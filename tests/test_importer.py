"""Task 6: round-trip `crg` export format + `graph import` action.

Covers :mod:`better_code_review_graph.importer`:

* Full round trip -- export a populated store as ``crg``, import into an
  empty store, get back the same node/edge counts.
* Idempotent re-import -- importing the same payload a second time updates
  rather than duplicates.
* Node/edge id namespacing by ``repo_id`` (and avoiding double-prefixing).
* ``source_text`` and summary metadata travel with the node.
* ``schema_version`` validation.
"""

from __future__ import annotations

import json

import pytest

from better_code_review_graph.exporter import export_graph
from better_code_review_graph.federation import RepoRegistry
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.importer import import_graph
from better_code_review_graph.parser import EdgeInfo, NodeInfo


@pytest.fixture
def seeded_store(tmp_path):
    """A small graph: 2 functions (one with source_text) + 1 CALLS edge."""
    db_path = tmp_path / "seeded.db"
    store = GraphStore(str(db_path))
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="foo",
            file_path="src/x.py",
            line_start=1,
            line_end=3,
            language="python",
            source_text="def foo():\n    return bar()\n",
        ),
        file_hash="hash1",
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="bar",
            file_path="src/x.py",
            line_start=5,
            line_end=6,
            language="python",
            source_text="def bar():\n    return 1\n",
        ),
        file_hash="hash1",
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source="src/x.py::foo",
            target="src/x.py::bar",
            file_path="src/x.py",
            line=2,
        )
    )
    yield store
    store.close()


def test_crg_export_import_round_trip(tmp_path, seeded_store):
    """Export `crg`, import into an EMPTY store, get back the same counts.

    Re-importing the same payload must be idempotent: 0 added, N updated.
    """
    payload = json.loads(export_graph(seeded_store, format="crg"))
    assert payload["schema_version"] == 1
    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)

        r1 = import_graph(fresh, reg, payload)
        assert r1["nodes_added"] == len(payload["nodes"])
        assert r1["nodes_updated"] == 0
        assert r1["edges_added"] == len(payload["edges"])
        assert r1["repo_id"] == payload["repo_id"]

        r2 = import_graph(fresh, reg, payload)
        assert r2["nodes_added"] == 0
        assert r2["nodes_updated"] == len(payload["nodes"])
        assert r2["edges_added"] == 0
    finally:
        fresh.close()


def test_import_rejects_unknown_schema_version(tmp_path, seeded_store):
    payload = json.loads(export_graph(seeded_store, format="crg"))
    payload["schema_version"] = 2

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        with pytest.raises(ValueError, match="schema_version"):
            import_graph(fresh, reg, payload)
    finally:
        fresh.close()


def test_import_namespaces_node_and_edge_ids(tmp_path, seeded_store):
    """Imported qualified names/edge endpoints are prefixed with repo_id::."""
    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        expected_foo_qn = f"{repo_id}::src/x.py::foo"
        expected_bar_qn = f"{repo_id}::src/x.py::bar"
        assert fresh.get_node(expected_foo_qn) is not None
        assert fresh.get_node(expected_bar_qn) is not None

        edges = fresh.get_edges_by_source(expected_foo_qn)
        assert len(edges) == 1
        assert edges[0].target_qualified == expected_bar_qn
    finally:
        fresh.close()


def test_import_avoids_double_prefixing_already_namespaced_payload(
    tmp_path, seeded_store
):
    """If the payload's ids already carry the repo_id:: prefix, don't re-prefix."""
    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]
    prefix = f"{repo_id}::"
    for node in payload["nodes"]:
        node["qualified_name"] = f"{prefix}{node['qualified_name']}"
        node["file_path"] = f"{prefix}{node['file_path']}"
    for edge in payload["edges"]:
        edge["source_qualified"] = f"{prefix}{edge['source_qualified']}"
        edge["target_qualified"] = f"{prefix}{edge['target_qualified']}"

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        # Must NOT be double-prefixed (repo_id::repo_id::...).
        assert fresh.get_node(f"{prefix}src/x.py::foo") is not None
        assert fresh.get_node(f"{prefix}{prefix}src/x.py::foo") is None
    finally:
        fresh.close()


def test_import_preserves_source_text(tmp_path, seeded_store):
    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        row = fresh._conn.execute(
            "SELECT source_text FROM nodes WHERE qualified_name = ?",
            (f"{repo_id}::src/x.py::foo",),
        ).fetchone()
        assert row is not None
        assert row["source_text"] == "def foo():\n    return bar()\n"
    finally:
        fresh.close()


def test_import_preserves_summary_metadata(tmp_path, seeded_store):
    """Summary/source_hash generated by graph(action='summarize') survive the round trip."""
    node = seeded_store.get_node("src/x.py::foo")
    seeded_store.update_summary(
        node.id, summary="Returns bar().", provider="gemini", source_hash="abc123"
    )

    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        row = fresh._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE qualified_name = ?",
            (f"{repo_id}::src/x.py::foo",),
        ).fetchone()
        assert row["summary"] == "Returns bar()."
        assert row["summary_provider"] == "gemini"
        assert row["source_hash"] == "abc123"
    finally:
        fresh.close()


def test_import_rolls_back_fully_when_a_later_node_is_malformed(tmp_path, seeded_store):
    """A malformed node AFTER a summary-carrying node must roll back to 0/0.

    Regression guard: GraphStore.update_summary() commits on its own, which
    used to end import_graph's `with store._conn:` transaction early --
    the summary-carrying node (and its `repos` row) stayed committed even
    when a later node in the same payload was malformed. Summary columns
    are now folded into the same INSERT as everything else, so nothing
    should survive a mid-loop failure.
    """
    node = seeded_store.get_node("src/x.py::foo")
    seeded_store.update_summary(
        node.id, summary="Returns bar().", provider="gemini", source_hash="abc123"
    )

    payload = json.loads(export_graph(seeded_store, format="crg"))
    # Guarantee processing order regardless of SQL row order: the
    # summary-carrying node ("foo") first, the corrupted one ("bar") second.
    nodes_by_name = {n["name"]: n for n in payload["nodes"]}
    payload["nodes"] = [nodes_by_name["foo"], nodes_by_name["bar"]]
    del payload["nodes"][1]["qualified_name"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        with pytest.raises(KeyError):
            import_graph(fresh, reg, payload)

        node_count = fresh._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        repo_count = fresh._conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0]
        assert node_count == 0
        assert repo_count == 0
    finally:
        fresh.close()


def test_import_idempotent_with_fresh_registry_each_call(tmp_path, seeded_store):
    """import_graph_dispatch builds a new RepoRegistry per call in practice --

    re-importing with a FRESHLY constructed registry (which reloads the
    already-registered repo_id from the `repos` table) must stay idempotent.
    """
    payload = json.loads(export_graph(seeded_store, format="crg"))

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        r1 = import_graph(fresh, RepoRegistry(fresh), payload)
        assert r1["nodes_added"] == len(payload["nodes"])

        # A brand-new registry reloads repos from the store, so this
        # exercises the "already registered" branch (not the stale-cache
        # INSERT OR IGNORE fallback the same-registry test above hits).
        r2 = import_graph(fresh, RepoRegistry(fresh), payload)
        assert r2["nodes_added"] == 0
        assert r2["nodes_updated"] == len(payload["nodes"])
    finally:
        fresh.close()


def test_import_registers_repo_in_registry(tmp_path, seeded_store):
    """The imported repo_id becomes a known participant for repo-scoped queries."""
    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        row = fresh._conn.execute(
            "SELECT repo_id FROM repos WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        assert row is not None
    finally:
        fresh.close()


def test_import_preserves_temporal_columns(tmp_path, seeded_store):
    """valid_from_sha/valid_to_sha must round-trip, not reset to defaults."""
    seeded_store._conn.execute(
        "UPDATE nodes SET valid_from_sha=?, valid_to_sha=? WHERE qualified_name=?",
        ("a" * 40, "b" * 40, "src/x.py::foo"),
    )
    seeded_store._conn.execute(
        "UPDATE edges SET valid_from_sha=?, valid_to_sha=? WHERE source_qualified=?",
        ("a" * 40, "b" * 40, "src/x.py::foo"),
    )
    seeded_store._conn.commit()

    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        node_row = fresh._conn.execute(
            "SELECT valid_from_sha, valid_to_sha FROM nodes WHERE qualified_name=?",
            (f"{repo_id}::src/x.py::foo",),
        ).fetchone()
        assert node_row["valid_from_sha"] == "a" * 40
        assert node_row["valid_to_sha"] == "b" * 40

        edge_row = fresh._conn.execute(
            "SELECT valid_from_sha, valid_to_sha FROM edges WHERE source_qualified=?",
            (f"{repo_id}::src/x.py::foo",),
        ).fetchone()
        assert edge_row["valid_from_sha"] == "a" * 40
        assert edge_row["valid_to_sha"] == "b" * 40
    finally:
        fresh.close()


def test_import_does_not_resurrect_tombstoned_node(tmp_path, seeded_store):
    """A node marked no-longer-live (valid_to_sha set) must NOT come back live."""
    seeded_store._conn.execute(
        "UPDATE nodes SET valid_to_sha=? WHERE qualified_name=?",
        ("deadbeef" * 5, "src/x.py::foo"),
    )
    seeded_store._conn.commit()

    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        qn = f"{repo_id}::src/x.py::foo"
        # get_node() defaults to as_of="" (currently-valid only) -- a
        # resurrected node would wrongly show up here.
        assert fresh.get_node(qn) is None

        row = fresh._conn.execute(
            "SELECT valid_to_sha FROM nodes WHERE qualified_name=?", (qn,)
        ).fetchone()
        assert row is not None
        assert row["valid_to_sha"] == "deadbeef" * 5
    finally:
        fresh.close()


def test_import_preserves_file_path_for_nodes_and_edges(tmp_path, seeded_store):
    """file_path stays the real source path (not namespaced) for nodes AND
    edges, so get_nodes_by_file still finds imported nodes and node/edge
    file_path still match for the same originating file."""
    payload = json.loads(export_graph(seeded_store, format="crg"))
    repo_id = payload["repo_id"]

    fresh = GraphStore(tmp_path / "fresh.db")
    try:
        reg = RepoRegistry(fresh)
        import_graph(fresh, reg, payload)

        nodes = fresh.get_nodes_by_file("src/x.py")
        assert {n.qualified_name for n in nodes} == {
            f"{repo_id}::src/x.py::foo",
            f"{repo_id}::src/x.py::bar",
        }
        for n in nodes:
            assert n.file_path == "src/x.py"

        edges = fresh.get_all_edges()
        assert len(edges) == 1
        assert edges[0].file_path == "src/x.py"
    finally:
        fresh.close()
