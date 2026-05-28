"""Phase 2 Task 9: GraphStore persists repo_id on nodes and edges.

Verifies that ``upsert_node`` / ``upsert_edge`` (and their batched
counterpart ``store_file_nodes_edges``) write the new ``repo_id``
column added in alembic revision ``003_federation``. Pre-Phase-2
NodeInfo/EdgeInfo objects without the ``repo_id`` attribute also need
to round-trip cleanly (``getattr(..., "repo_id", "")`` fallback).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


def _new_store() -> tuple[GraphStore, Path]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return GraphStore(tmp.name), Path(tmp.name)


def test_upsert_node_persists_repo_id() -> None:
    """``upsert_node`` writes repo_id and round-trips through SQL."""
    store, db_path = _new_store()
    try:
        node = NodeInfo(
            kind="Function",
            name="foo",
            file_path="/x/y.py",
            line_start=1,
            line_end=5,
            language="python",
            repo_id="my-repo-12345678",
        )
        store.upsert_node(node)
        store.commit()

        row = store._conn.execute(
            "SELECT repo_id FROM nodes WHERE qualified_name = ?",
            ("/x/y.py::foo",),
        ).fetchone()
        assert row is not None
        assert row["repo_id"] == "my-repo-12345678"
    finally:
        store.close()
        db_path.unlink(missing_ok=True)


def test_upsert_edge_persists_repo_id() -> None:
    """``upsert_edge`` writes repo_id and round-trips through SQL."""
    store, db_path = _new_store()
    try:
        edge = EdgeInfo(
            kind="CALLS",
            source="/x/y.py::a",
            target="/x/y.py::b",
            file_path="/x/y.py",
            line=10,
            repo_id="my-repo-12345678",
        )
        store.upsert_edge(edge)
        store.commit()

        row = store._conn.execute(
            "SELECT repo_id FROM edges WHERE source_qualified = ? AND target_qualified = ?",
            ("/x/y.py::a", "/x/y.py::b"),
        ).fetchone()
        assert row is not None
        assert row["repo_id"] == "my-repo-12345678"
    finally:
        store.close()
        db_path.unlink(missing_ok=True)


def test_upsert_node_default_repo_id_is_empty_string() -> None:
    """Backwards-compat: NodeInfo without explicit repo_id stores ''."""
    store, db_path = _new_store()
    try:
        node = NodeInfo(
            kind="Function",
            name="bar",
            file_path="/p.py",
            line_start=1,
            line_end=2,
            language="python",
        )
        store.upsert_node(node)
        store.commit()

        row = store._conn.execute(
            "SELECT repo_id FROM nodes WHERE qualified_name = ?",
            ("/p.py::bar",),
        ).fetchone()
        assert row is not None
        assert row["repo_id"] == ""
    finally:
        store.close()
        db_path.unlink(missing_ok=True)


def test_store_file_nodes_edges_persists_repo_id() -> None:
    """Batched insertion path also writes repo_id for nodes and edges."""
    store, db_path = _new_store()
    try:
        nodes = [
            NodeInfo(
                kind="File",
                name="/x.py",
                file_path="/x.py",
                line_start=1,
                line_end=10,
                language="python",
                repo_id="abc-12345678",
            ),
            NodeInfo(
                kind="Function",
                name="foo",
                file_path="/x.py",
                line_start=2,
                line_end=4,
                language="python",
                repo_id="abc-12345678",
            ),
        ]
        edges = [
            EdgeInfo(
                kind="CONTAINS",
                source="/x.py",
                target="/x.py::foo",
                file_path="/x.py",
                line=2,
                repo_id="abc-12345678",
            ),
        ]
        store.store_file_nodes_edges("/x.py", nodes, edges)

        rows = store._conn.execute(
            "SELECT repo_id FROM nodes WHERE file_path = ?", ("/x.py",)
        ).fetchall()
        assert rows
        for r in rows:
            assert r["repo_id"] == "abc-12345678"

        edge_rows = store._conn.execute(
            "SELECT repo_id FROM edges WHERE file_path = ?", ("/x.py",)
        ).fetchall()
        assert edge_rows
        for r in edge_rows:
            assert r["repo_id"] == "abc-12345678"
    finally:
        store.close()
        db_path.unlink(missing_ok=True)


def test_upsert_node_legacy_object_without_repo_id_attr() -> None:
    """Legacy callers passing a NodeInfo-shaped object lacking ``repo_id`` work.

    The graph layer uses ``getattr(node, "repo_id", "")`` so callers
    that haven't been updated continue to work without a code change.
    """
    store, db_path = _new_store()
    try:
        # Build a stand-in object that mimics NodeInfo's surface but
        # without the repo_id attribute (simulates a pre-Task-9 caller).
        class LegacyNode:
            kind = "Function"
            name = "legacy"
            file_path = "/legacy.py"
            line_start = 1
            line_end = 3
            language = "python"
            parent_name = None
            params = None
            return_type = None
            modifiers = None
            is_test = False
            extra: dict = {}
            source_text = None

        store.upsert_node(LegacyNode())  # ty: ignore[invalid-argument-type]
        store.commit()

        row = store._conn.execute(
            "SELECT repo_id FROM nodes WHERE qualified_name = ?",
            ("/legacy.py::legacy",),
        ).fetchone()
        assert row is not None
        assert row["repo_id"] == ""
    finally:
        store.close()
        db_path.unlink(missing_ok=True)
