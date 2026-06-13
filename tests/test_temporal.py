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
(``upsert_edge`` analogue, repo_id propagation, and post-supersede history queries).
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

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
        kind="FUNCTION",
        name=name,
        file_path=file_path,
        line_start=10,
        line_end=15,
        language="python",
        parent_name="",
        params=None,
        return_type=None,
        modifiers="[]",  # TemporalIndex expects string for SQLite storage
        is_test=False,
        extra={},
        source_text=source_text,
        repo_id=repo_id,
    )


def _make_edge(
    source: str = "src/m.py::foo",
    target: str = "src/m.py::bar",
    *,
    line: int = 12,
    repo_id: str = "",
) -> EdgeInfo:
    """Build an EdgeInfo with the fields TemporalIndex consumes."""
    return EdgeInfo(
        source=source,
        target=target,
        kind="CALLS",
        file_path="src/m.py",
        line=line,
        extra={},
        repo_id=repo_id,
    )


# ---------------------------------------------------------------------------
# (1) Fresh INSERT path
# ---------------------------------------------------------------------------


def test_upsert_node_inserts_when_no_prior_row(tmp_graph_store: GraphStore) -> None:
    """No currently-valid row → INSERT with valid_from_sha=current, valid_to_sha=NULL."""
    idx = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    node = _make_function_node()
    result = idx.upsert_node(node)

    assert result == TemporalUpsertResult(action="inserted", closed_out_count=0)

    rows = tmp_graph_store._conn.execute(
        "SELECT qualified_name, valid_from_sha, valid_to_sha, source_text "
        "FROM nodes WHERE qualified_name = 'src/m.py::foo'"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["valid_from_sha"] == _SHA_A
    assert row["valid_to_sha"] is None
    assert row["source_text"] == "def foo():\n    return 1\n"


# ---------------------------------------------------------------------------
# (2) Unchanged path (metadata refresh)
# ---------------------------------------------------------------------------


def test_upsert_node_unchanged_when_source_matches(tmp_graph_store: GraphStore) -> None:
    """Currently-valid row exists, source identical → UPDATE metadata, keep valid_from."""
    idx_a = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="v1"))

    idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    # Different line numbers — that's metadata, not divergence.
    node = _make_function_node(source_text="v1")
    node.line_start = 99
    result = idx_b.upsert_node(node)

    assert result == TemporalUpsertResult(action="unchanged", closed_out_count=0)

    rows = tmp_graph_store._conn.execute(
        "SELECT line_start, valid_from_sha, valid_to_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo'"
    ).fetchall()
    assert len(rows) == 1
    # valid_from_sha pinned to first observation (sha_a).
    assert rows[0]["valid_from_sha"] == _SHA_A
    assert rows[0]["valid_to_sha"] is None
    # Metadata refreshed.
    assert rows[0]["line_start"] == 99


# ---------------------------------------------------------------------------
# (3) Divergence path (supersede)
# ---------------------------------------------------------------------------


def test_upsert_node_supersedes_when_source_diverges(
    tmp_graph_store: GraphStore,
) -> None:
    """Currently-valid row exists, source diverged → close out prior + INSERT new."""
    idx_a = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="def foo():\n    return 1\n"))

    idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    node = _make_function_node(source_text="def foo():\n    return 2\n")
    result = idx_b.upsert_node(node)

    assert result == TemporalUpsertResult(action="superseded", closed_out_count=1)

    rows = tmp_graph_store._conn.execute(
        "SELECT valid_from_sha, valid_to_sha, source_text FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    # Row 1: closed out with sha_b.
    assert rows[0]["valid_from_sha"] == _SHA_A
    assert rows[0]["valid_to_sha"] == _SHA_B
    assert rows[0]["source_text"] == "def foo():\n    return 1\n"
    # Row 2: new version valid from sha_b, valid_to_sha = NULL.
    assert rows[1]["valid_from_sha"] == _SHA_B
    assert rows[1]["valid_to_sha"] is None
    assert rows[1]["source_text"] == "def foo():\n    return 2\n"


# ---------------------------------------------------------------------------
# (4) Action string contract
# ---------------------------------------------------------------------------


def test_upsert_node_returns_correct_action_string(tmp_graph_store: GraphStore) -> None:
    """Action strings are exactly the documented set."""
    idx_a = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    r1 = idx_a.upsert_node(_make_function_node(source_text="v1"))
    assert r1.action == "inserted"

    idx_a2 = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    r2 = idx_a2.upsert_node(_make_function_node(source_text="v1"))
    assert r2.action == "unchanged"

    idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    r3 = idx_b.upsert_node(_make_function_node(source_text="v2"))
    assert r3.action == "superseded"


# ---------------------------------------------------------------------------
# (5) closed_out_count contract
# ---------------------------------------------------------------------------


def test_upsert_node_closed_out_count(tmp_graph_store: GraphStore) -> None:
    """``closed_out_count`` is 1 on supersede, 0 otherwise."""
    idx_a = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    r1 = idx_a.upsert_node(_make_function_node(source_text="v1"))
    assert r1.closed_out_count == 0

    idx_a2 = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    r2 = idx_a2.upsert_node(_make_function_node(source_text="v1"))
    assert r2.closed_out_count == 0

    idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    r3 = idx_b.upsert_node(_make_function_node(source_text="v2"))
    assert r3.closed_out_count == 1


# ---------------------------------------------------------------------------
# (6) Edge — fresh insert
# ---------------------------------------------------------------------------


def test_upsert_edge_inserts_when_no_prior_row(tmp_graph_store: GraphStore) -> None:
    """First edge observation → INSERT with valid_from_sha=current, valid_to_sha=NULL."""
    idx = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    edge = _make_edge()
    result = idx.upsert_edge(edge)

    assert result == TemporalUpsertResult(action="inserted", closed_out_count=0)

    rows = tmp_graph_store._conn.execute(
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


def test_upsert_edge_unchanged_when_already_present(
    tmp_graph_store: GraphStore,
) -> None:
    """Edges identity by (src, dst, kind); second upsert always reports unchanged."""
    idx_a = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    idx_a.upsert_edge(_make_edge(line=5))

    idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    # Different line — that's metadata, not identity. Expected: unchanged + UPDATE.
    result = idx_b.upsert_edge(_make_edge(line=42))

    assert result.action == "unchanged"
    assert result.closed_out_count == 0

    rows = tmp_graph_store._conn.execute(
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


# (8) repo_id survives both insert + supersede paths
# ---------------------------------------------------------------------------


def test_temporal_index_preserves_repo_id_field(tmp_graph_store: GraphStore) -> None:
    """Federated build: repo_id flows through the insert and supersede branches."""
    idx_a = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(source_text="v1", repo_id="my-repo"),
    )

    idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    idx_b.upsert_node(
        _make_function_node(source_text="v2", repo_id="my-repo"),
    )

    rows = tmp_graph_store._conn.execute(
        "SELECT repo_id, valid_from_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["repo_id"] == "my-repo"
    assert rows[1]["repo_id"] == "my-repo"

    # Edge insert path also propagates repo_id.
    edge_idx = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    edge_idx.upsert_edge(_make_edge(repo_id="my-repo"))
    edge_rows = tmp_graph_store._conn.execute(
        "SELECT repo_id FROM edges WHERE source_qualified = 'src/m.py::foo' "
        "AND target_qualified = 'src/m.py::bar' AND kind = 'CALLS'"
    ).fetchall()
    assert len(edge_rows) == 1
    assert edge_rows[0]["repo_id"] == "my-repo"

    # Edge update path also propagates repo_id.
    edge_idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    edge_idx_b.upsert_edge(_make_edge(repo_id="my-repo", line=99))
    edge_rows = tmp_graph_store._conn.execute(
        "SELECT repo_id, line FROM edges WHERE source_qualified = 'src/m.py::foo' "
        "AND target_qualified = 'src/m.py::bar' AND kind = 'CALLS'"
    ).fetchall()
    assert edge_rows[0]["repo_id"] == "my-repo"
    assert edge_rows[0]["line"] == 99


# ---------------------------------------------------------------------------
# (9) History queryable after supersede
# ---------------------------------------------------------------------------


def test_temporal_index_can_query_history_after_supersede(
    tmp_graph_store: GraphStore,
) -> None:
    """Both rows queryable post-supersede: latest via valid_to_sha IS NULL."""
    idx_a = TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="v1"))

    idx_b = TemporalIndex(tmp_graph_store, current_sha=_SHA_B)
    idx_b.upsert_node(_make_function_node(source_text="v2"))

    idx_c = TemporalIndex(tmp_graph_store, current_sha=_SHA_C)
    idx_c.upsert_node(_make_function_node(source_text="v3"))

    # Currently-valid row.
    current = tmp_graph_store._conn.execute(
        "SELECT source_text, valid_from_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::foo' AND valid_to_sha IS NULL"
    ).fetchall()
    assert len(current) == 1
    assert current[0]["source_text"] == "v3"
    assert current[0]["valid_from_sha"] == _SHA_C

    # Historical rows (closed out).
    historical = tmp_graph_store._conn.execute(
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


# ---------------------------------------------------------------------------
# (10) Internal utility functions: _hash_source and _quote_identifier
# ---------------------------------------------------------------------------


def test_hash_source_basics() -> None:
    """_hash_source handles empty/None and produces stable hex for text."""
    from better_code_review_graph.temporal import _hash_source

    assert _hash_source(None) == ""
    assert _hash_source("") == ""
    # Stable SHA-256 for "abc"
    expected = hashlib.sha256(b"abc").hexdigest()
    assert _hash_source("abc") == expected


def test_quote_identifier_basics() -> None:
    """_quote_identifier wraps in double quotes and escapes existing quotes."""
    from better_code_review_graph.temporal import _quote_identifier

    assert _quote_identifier("foo") == '"foo"'
    assert _quote_identifier('f"o"o') == '"f""o""o"'


# ---------------------------------------------------------------------------
# (11) Schema safety check
# ---------------------------------------------------------------------------


def test_ensure_temporal_friendly_schema_raises_on_unsafe_column(
    tmp_graph_store: GraphStore,
) -> None:
    """Detection of unsafe column names (non-alphanumeric) triggers RuntimeError."""
    # Mock the cursor to return an "unsafe" column name in the PRAGMA table_info result.
    # col_info: (cid, name, typ, notnull, dflt, pk)
    unsafe_col = (0, "unsafe column!", "TEXT", 0, None, 0)

    mock_conn = MagicMock()
    # Mock return values for execute() calls.
    # We need enough returns to cover the DROP, CREATE, and other setup calls.
    mock_conn.execute.side_effect = [
        MagicMock(fetchone=lambda: ("sqlite_autoindex_nodes_1",)),  # legacy check
        MagicMock(fetchall=lambda: [unsafe_col]),  # PRAGMA table_info
    ]

    with patch.object(tmp_graph_store, "_conn", mock_conn):
        with pytest.raises(RuntimeError, match="Unsafe column name detected"):
            TemporalIndex(tmp_graph_store, current_sha=_SHA_A)


# ---------------------------------------------------------------------------
# (12) Coverage for column-presence index logic
# ---------------------------------------------------------------------------


def test_ensure_temporal_friendly_schema_handles_missing_columns_gracefully(
    tmp_graph_store: GraphStore,
) -> None:
    """Detection of repo_id and valid_from_sha for indexing is safe if they are missing."""
    # Mock schema WITHOUT repo_id and WITHOUT valid_from_sha.
    # col_info: (cid, name, typ, notnull, dflt, pk)
    cols = [
        (0, "id", "INTEGER", 1, None, 1),
        (1, "qualified_name", "TEXT", 1, None, 0),
    ]

    mock_conn = MagicMock()
    # We need to mock several calls in the rebuild path.
    mock_conn.execute.side_effect = [
        MagicMock(fetchone=lambda: ("sqlite_autoindex_nodes_1",)),  # legacy check
        MagicMock(fetchall=lambda: cols),  # PRAGMA table_info
        MagicMock(),  # DROP TABLE IF EXISTS nodes_temporal_new
        MagicMock(),  # CREATE TABLE nodes_temporal_new
        MagicMock(),  # INSERT INTO nodes_temporal_new
        MagicMock(),  # DROP TABLE nodes
        MagicMock(),  # ALTER TABLE nodes_temporal_new RENAME TO nodes
        MagicMock(),  # CREATE INDEX idx_nodes_file
        MagicMock(),  # CREATE INDEX idx_nodes_kind
        MagicMock(),  # CREATE INDEX idx_nodes_qualified
        MagicMock(),  # CREATE INDEX idx_nodes_source_hash
        MagicMock(),  # CREATE UNIQUE INDEX idx_nodes_qualified_active
    ]

    with patch.object(tmp_graph_store, "_conn", mock_conn):
        TemporalIndex(tmp_graph_store, current_sha=_SHA_A)
        # Verify that we did NOT attempt to create the repo or temporal indexes.
        for call in mock_conn.execute.call_args_list:
            sql = call[0][0]
            assert "idx_nodes_repo_kind" not in sql
            assert "idx_nodes_temporal" not in sql
