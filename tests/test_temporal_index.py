"""Tests for the TemporalIndex (Phase 3 Task 8).

The temporal index wraps :class:`GraphStore` with close-out + supersede
semantics across commits. Where the legacy ``upsert_node`` path uses
``ON CONFLICT(qualified_name) DO UPDATE`` (overwriting in place, losing
history), :class:`TemporalIndex.upsert_node` instead:

* Inserts a new row when no currently-valid row exists for the
  (qualified_name) key.
* Leaves the existing row in place — only refreshing scalar metadata —
  when the source text is unchanged. The ``valid_from_sha`` is NOT
  rotated because the row is still the same logical version, just
  re-observed.
* Closes out the prior currently-valid row (sets
  ``valid_to_sha = current_sha``) AND inserts a new row when the source
  text diverges. The old row remains queryable as historical state.

These tests pin those three branches plus the supporting machinery
(``upsert_edge`` analogue,
repo_id propagation, and post-supersede history queries).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.temporal import TemporalIndex, TemporalUpsertResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SHA_A = "a" * 40
_SHA_B = "b" * 40
_SHA_C = "c" * 40


def _make_function_node(
    name: str = "foo",
    *,
    file_path: str = "src/m.py",
    source_text: str | None = "def foo():\n    return 1\n",
    repo_id: str = "",
) -> NodeInfo:
    """Build a Function NodeInfo with the fields TemporalIndex consumes."""
    return NodeInfo(
        kind="Function",
        name=name,
        file_path=file_path,
        line_start=1,
        line_end=2,
        language="python",
        parent_name=None,
        params="()",
        return_type=None,
        modifiers=None,
        is_test=False,
        extra={},
        source_text=source_text,
        repo_id=repo_id,
    )


def _make_edge(
    *,
    source: str = "src/m.py::foo",
    target: str = "src/m.py::bar",
    kind: str = "CALLS",
    file_path: str = "src/m.py",
    line: int = 5,
    repo_id: str = "",
) -> EdgeInfo:
    return EdgeInfo(
        kind=kind,
        source=source,
        target=target,
        file_path=file_path,
        line=line,
        extra={},
        repo_id=repo_id,
    )


@pytest.fixture
def store(tmp_path: Path):
    """File-backed :class:`GraphStore` so the alembic migration runs end-to-end."""
    db_path = tmp_path / "graph.db"
    s = GraphStore(str(db_path))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# (1) Fresh insert — no prior currently-valid row
# ---------------------------------------------------------------------------


def test_upsert_node_inserts_when_no_prior_row(store: GraphStore) -> None:
    """First observation of a node → INSERT with valid_from_sha=current, valid_to_sha=NULL."""
    idx = TemporalIndex(store, current_sha=_SHA_A)
    node = _make_function_node()
    result = idx.upsert_node(node)

    assert result == TemporalUpsertResult(action="inserted", closed_out_count=0)

    rows = store._conn.execute(
        "SELECT qualified_name, valid_from_sha, valid_to_sha, source_text "
        "FROM nodes WHERE qualified_name = 'src/m.py::foo'"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["valid_from_sha"] == _SHA_A
    assert row["valid_to_sha"] is None
    assert row["source_text"] == "def foo():\n    return 1\n"


# ---------------------------------------------------------------------------
# (2) Source unchanged — re-upsert leaves the row alone
# ---------------------------------------------------------------------------


def test_upsert_node_unchanged_when_source_identical(store: GraphStore) -> None:
    """Second upsert with same source text → no new row, valid_from_sha unchanged."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    node = _make_function_node()
    idx_a.upsert_node(node)

    # Re-observe the same node at a later commit.
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    result = idx_b.upsert_node(node)

    assert result.action == "unchanged"
    assert result.closed_out_count == 0

    rows = store._conn.execute(
        "SELECT valid_from_sha, valid_to_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' ORDER BY id"
    ).fetchall()
    # Single row only — no supersede.
    assert len(rows) == 1
    # valid_from_sha pinned to the FIRST observation; we did NOT rotate it.
    assert rows[0]["valid_from_sha"] == _SHA_A
    assert rows[0]["valid_to_sha"] is None


# ---------------------------------------------------------------------------
# (3) Source diverged — close-out + insert
# ---------------------------------------------------------------------------


def test_upsert_node_supersedes_when_source_diverges(store: GraphStore) -> None:
    """Source text changed → prior row closed out, new row inserted."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="def foo():\n    return 1\n"))

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    result = idx_b.upsert_node(
        _make_function_node(source_text="def foo():\n    return 2\n")
    )

    assert result.action == "superseded"
    assert result.closed_out_count == 1

    rows = store._conn.execute(
        "SELECT valid_from_sha, valid_to_sha, source_text FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2

    # Old row: closed out at sha_b.
    assert rows[0]["valid_from_sha"] == _SHA_A
    assert rows[0]["valid_to_sha"] == _SHA_B
    assert rows[0]["source_text"] == "def foo():\n    return 1\n"
    # New row: valid_from_sha = current_sha, valid_to_sha = NULL.
    assert rows[1]["valid_from_sha"] == _SHA_B
    assert rows[1]["valid_to_sha"] is None
    assert rows[1]["source_text"] == "def foo():\n    return 2\n"


# ---------------------------------------------------------------------------
# (4) Action string contract
# ---------------------------------------------------------------------------


def test_upsert_node_returns_correct_action_string(store: GraphStore) -> None:
    """Action strings are exactly the documented set."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    r1 = idx_a.upsert_node(_make_function_node(source_text="v1"))
    assert r1.action == "inserted"

    idx_a2 = TemporalIndex(store, current_sha=_SHA_A)
    r2 = idx_a2.upsert_node(_make_function_node(source_text="v1"))
    assert r2.action == "unchanged"

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    r3 = idx_b.upsert_node(_make_function_node(source_text="v2"))
    assert r3.action == "superseded"


# ---------------------------------------------------------------------------
# (5) closed_out_count contract
# ---------------------------------------------------------------------------


def test_upsert_node_closed_out_count(store: GraphStore) -> None:
    """``closed_out_count`` is 1 on supersede, 0 otherwise."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    r1 = idx_a.upsert_node(_make_function_node(source_text="v1"))
    assert r1.closed_out_count == 0

    idx_a2 = TemporalIndex(store, current_sha=_SHA_A)
    r2 = idx_a2.upsert_node(_make_function_node(source_text="v1"))
    assert r2.closed_out_count == 0

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    r3 = idx_b.upsert_node(_make_function_node(source_text="v2"))
    assert r3.closed_out_count == 1


# ---------------------------------------------------------------------------
# (6) Edge — fresh insert
# ---------------------------------------------------------------------------


def test_upsert_edge_inserts_when_no_prior_row(store: GraphStore) -> None:
    """First edge observation → INSERT with valid_from_sha=current, valid_to_sha=NULL."""
    idx = TemporalIndex(store, current_sha=_SHA_A)
    edge = _make_edge()
    result = idx.upsert_edge(edge)

    assert result == TemporalUpsertResult(action="inserted", closed_out_count=0)

    rows = store._conn.execute(
        "SELECT source_qualified, target_qualified, kind, valid_from_sha, valid_to_sha "
        "FROM edges WHERE source_qualified = 'src/m.py::foo' "
        "AND target_qualified = 'src/m.py::bar' AND kind = 'CALLS'"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["valid_from_sha"] == _SHA_A
    assert row["valid_to_sha"] is None


# ---------------------------------------------------------------------------
# (7) Edge — second upsert is "unchanged" (no source-text divergence semantics)
# ---------------------------------------------------------------------------


def test_upsert_edge_unchanged_when_already_present(store: GraphStore) -> None:
    """Edges identity by (src, dst, kind); second upsert always reports unchanged."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_edge(_make_edge(line=5))

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    # Different line — that's metadata, not identity. Expected: unchanged + UPDATE.
    result = idx_b.upsert_edge(_make_edge(line=42))

    assert result.action == "unchanged"
    assert result.closed_out_count == 0

    rows = store._conn.execute(
        "SELECT id, line, valid_from_sha, valid_to_sha FROM edges "
        "WHERE source_qualified = 'src/m.py::foo' "
        "AND target_qualified = 'src/m.py::bar' AND kind = 'CALLS' "
        "ORDER BY id"
    ).fetchall()
    assert len(rows) == 1
    # valid_from_sha pinned to first observation.
    assert rows[0]["valid_from_sha"] == _SHA_A
    assert rows[0]["valid_to_sha"] is None
    # Line metadata refreshed on update path.
    assert rows[0]["line"] == 42


# ---------------------------------------------------------------------------
# (10) repo_id survives both insert + supersede paths
# ---------------------------------------------------------------------------


def test_temporal_index_preserves_repo_id_field(store: GraphStore) -> None:
    """Federated build: repo_id flows through the insert and supersede branches."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(source_text="v1", repo_id="my-repo"),
    )

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(
        _make_function_node(source_text="v2", repo_id="my-repo"),
    )

    rows = store._conn.execute(
        "SELECT repo_id, valid_from_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["repo_id"] == "my-repo"
    assert rows[1]["repo_id"] == "my-repo"

    # Edge insert path also propagates repo_id.
    edge_idx = TemporalIndex(store, current_sha=_SHA_A)
    edge_idx.upsert_edge(_make_edge(repo_id="my-repo"))
    edge_rows = store._conn.execute(
        "SELECT repo_id FROM edges WHERE source_qualified = 'src/m.py::foo' "
        "AND target_qualified = 'src/m.py::bar' AND kind = 'CALLS'"
    ).fetchall()
    assert len(edge_rows) == 1
    assert edge_rows[0]["repo_id"] == "my-repo"

    # Edge update path also propagates repo_id.
    edge_idx_b = TemporalIndex(store, current_sha=_SHA_B)
    edge_idx_b.upsert_edge(_make_edge(repo_id="my-repo", line=99))
    edge_rows = store._conn.execute(
        "SELECT repo_id, line FROM edges WHERE source_qualified = 'src/m.py::foo' "
        "AND target_qualified = 'src/m.py::bar' AND kind = 'CALLS'"
    ).fetchall()
    assert edge_rows[0]["repo_id"] == "my-repo"
    assert edge_rows[0]["line"] == 99


# ---------------------------------------------------------------------------
# (11) History queryable after supersede
# ---------------------------------------------------------------------------


def test_temporal_index_can_query_history_after_supersede(store: GraphStore) -> None:
    """Both rows queryable post-supersede: latest via valid_to_sha IS NULL."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="v1"))

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(_make_function_node(source_text="v2"))

    idx_c = TemporalIndex(store, current_sha=_SHA_C)
    idx_c.upsert_node(_make_function_node(source_text="v3"))

    # Currently-valid row.
    current = store._conn.execute(
        "SELECT source_text, valid_from_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' AND valid_to_sha IS NULL"
    ).fetchall()
    assert len(current) == 1
    assert current[0]["source_text"] == "v3"
    assert current[0]["valid_from_sha"] == _SHA_C

    # Historical rows (closed out).
    historical = store._conn.execute(
        "SELECT source_text, valid_from_sha, valid_to_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' AND valid_to_sha IS NOT NULL "
        "ORDER BY valid_from_sha"
    ).fetchall()
    assert len(historical) == 2
    # First version: valid from sha_a, closed at sha_b.
    assert historical[0]["source_text"] == "v1"
    assert historical[0]["valid_from_sha"] == _SHA_A
    assert historical[0]["valid_to_sha"] == _SHA_B
    # Second version: valid from sha_b, closed at sha_c.
    assert historical[1]["source_text"] == "v2"
    assert historical[1]["valid_from_sha"] == _SHA_B
    assert historical[1]["valid_to_sha"] == _SHA_C
