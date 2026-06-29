"""Phase 3 Task 9: ``as_of`` + ``diff`` cross-cutting query parameters.

These tests pin the behaviour of the temporal query layer:

* Default (``as_of=""``) must return ONLY currently-valid rows
  (``valid_to_sha IS NULL``). Historical rows that were closed-out by
  a later supersede must be excluded.
* ``as_of=<sha>`` returns the row whose ``valid_from_sha`` matches
  the requested SHA — the "snapshot at SHA" semantic. This is the
  Task 9 MVP scope; full ancestor-walk against the ``commits`` table
  is deferred.
* ``diff(from_sha, to_sha)`` returns ``added`` / ``removed`` / ``modified``
  buckets keyed off ``valid_from_sha`` / ``valid_to_sha``. ``modified``
  is the intersection of "closed at to_sha" and "introduced at to_sha"
  for the same qualified_name (i.e. supersede); pure adds and pure
  removes do not show up there.

Fixtures use :class:`TemporalIndex` to set up multi-version state so
the tests exercise the same code path the v2 ingest layer will go
through. The legacy ``GraphStore.upsert_node`` overwrite path is not
suitable for these tests — it loses history by design.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.temporal import TemporalIndex
from better_code_review_graph.tools import (
    diff_graph,
    get_impact_radius,
    semantic_search_nodes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SHA_A = "a" * 40
_SHA_B = "b" * 40
_SHA_C = "c" * 40


def _make_function_node(
    name: str = "retry",
    *,
    file_path: str = "src/m.py",
    source_text: str = "def retry():\n    return 1\n",
    repo_id: str = "",
) -> NodeInfo:
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


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    """Build a fake repo workspace with .git + .code-review-graph/graph.db."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".git").mkdir()
    crg_dir = ws / ".code-review-graph"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")
    yield ws


@pytest.fixture
def store(workspace: Path) -> Iterator[GraphStore]:
    """File-backed GraphStore inside the fake workspace."""
    db_path = workspace / ".code-review-graph" / "graph.db"
    s = GraphStore(str(db_path))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# (1) Default search returns only currently-valid rows
# ---------------------------------------------------------------------------


def test_query_search_default_returns_currently_valid_only(
    workspace: Path, store: GraphStore
) -> None:
    """Insert at sha1, supersede at sha2 -- default search returns only sha2 row."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="def retry():\n    return 1\n"))

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(_make_function_node(source_text="def retry():\n    return 2\n"))

    # Two physical rows now exist for the same qualified_name; one closed
    # out at sha_b and one currently valid (valid_to_sha IS NULL).
    rows = store._conn.execute(
        "SELECT valid_from_sha, valid_to_sha FROM nodes "
        "WHERE qualified_name = 'src/m.py::retry' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["valid_from_sha"] == _SHA_A
    assert rows[0]["valid_to_sha"] == _SHA_B
    assert rows[1]["valid_from_sha"] == _SHA_B
    assert rows[1]["valid_to_sha"] is None

    store.close()  # release WAL so the tools layer can reopen.

    result = semantic_search_nodes(query="retry", repo_root=str(workspace))
    assert result["status"] == "ok"
    # Only the currently-valid row should surface; historical row is hidden.
    qns = [r.get("qualified_name") for r in result["results"]]
    assert qns.count("src/m.py::retry") == 1


# ---------------------------------------------------------------------------
# (2) as_of returns historical row at the requested sha
# ---------------------------------------------------------------------------


def test_query_search_as_of_returns_historical_row(
    workspace: Path, store: GraphStore
) -> None:
    """as_of=sha_a returns the row introduced at sha_a even after supersede."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="def retry():\n    return 1\n"))
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(_make_function_node(source_text="def retry():\n    return 2\n"))
    store.close()

    result = semantic_search_nodes(
        query="retry", repo_root=str(workspace), as_of=_SHA_A
    )
    assert result["status"] == "ok"
    qns = [r.get("qualified_name") for r in result["results"]]
    # The historical row introduced at sha_a is what we asked for.
    assert "src/m.py::retry" in qns


# ---------------------------------------------------------------------------
# (3) Unknown sha returns empty
# ---------------------------------------------------------------------------


def test_query_search_as_of_returns_empty_for_unknown_sha(
    workspace: Path, store: GraphStore
) -> None:
    """as_of=non-existent-sha matches no rows."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node())
    store.close()

    result = semantic_search_nodes(
        query="retry", repo_root=str(workspace), as_of=_SHA_C
    )
    assert result["status"] == "ok"
    assert result["results"] == []


# ---------------------------------------------------------------------------
# (4) diff requires both from_sha and to_sha
# ---------------------------------------------------------------------------


def test_diff_graph_requires_both_shas(workspace: Path, store: GraphStore) -> None:
    """diff_graph returns error when from_sha or to_sha is missing."""
    store.close()
    err = diff_graph(repo_root=str(workspace), from_sha="", to_sha=_SHA_B)
    assert "error" in err
    err = diff_graph(repo_root=str(workspace), from_sha=_SHA_A, to_sha="")
    assert "error" in err


# ---------------------------------------------------------------------------
# (5) Added: rows introduced at to_sha
# ---------------------------------------------------------------------------


def test_diff_graph_returns_added_nodes(workspace: Path, store: GraphStore) -> None:
    """A node first introduced at to_sha shows up in `added`."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(name="old_func"))
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(_make_function_node(name="new_func"))
    store.close()

    result = diff_graph(repo_root=str(workspace), from_sha=_SHA_A, to_sha=_SHA_B)
    assert result["from_sha"] == _SHA_A
    assert result["to_sha"] == _SHA_B
    added_qns = [r["qualified_name"] for r in result["added"]]
    assert "src/m.py::new_func" in added_qns
    assert "src/m.py::old_func" not in added_qns


# ---------------------------------------------------------------------------
# (6) Removed: rows closed at to_sha with no replacement
# ---------------------------------------------------------------------------


def test_diff_graph_returns_removed_nodes(workspace: Path, store: GraphStore) -> None:
    """A node closed at to_sha (no new row at to_sha) shows up in `removed`."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(name="vanishing"))

    # Sweep the file at sha_b with no observation -> closes out vanishing.
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.close_missing_nodes(file_path="src/m.py", observed_qualified=set())
    store.close()

    result = diff_graph(repo_root=str(workspace), from_sha=_SHA_A, to_sha=_SHA_B)
    removed_qns = [r["qualified_name"] for r in result["removed"]]
    assert "src/m.py::vanishing" in removed_qns
    # Not in added (no replacement was inserted at sha_b).
    added_qns = [r["qualified_name"] for r in result["added"]]
    assert "src/m.py::vanishing" not in added_qns


# ---------------------------------------------------------------------------
# (7) Modified: closed AND new row with same qualified_name at to_sha
# ---------------------------------------------------------------------------


def test_diff_graph_returns_modified_nodes(workspace: Path, store: GraphStore) -> None:
    """Supersede at to_sha (close-out + new row, same qualified_name) -> modified."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(_make_function_node(source_text="def retry():\n    return 1\n"))
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(_make_function_node(source_text="def retry():\n    return 2\n"))
    store.close()

    result = diff_graph(repo_root=str(workspace), from_sha=_SHA_A, to_sha=_SHA_B)
    modified_qns = [r["qualified_name"] for r in result["modified"]]
    assert "src/m.py::retry" in modified_qns
    # Modified rows must NOT also appear in added or removed.
    added_qns = [r["qualified_name"] for r in result["added"]]
    removed_qns = [r["qualified_name"] for r in result["removed"]]
    assert "src/m.py::retry" not in added_qns
    assert "src/m.py::retry" not in removed_qns


# ---------------------------------------------------------------------------
# (8) Repo filter narrows diff to the requested repo_id
# ---------------------------------------------------------------------------


def test_diff_graph_with_repo_filter(workspace: Path, store: GraphStore) -> None:
    """diff_graph(... repo=...) excludes rows from other repos."""
    repo_a = "repo_a-aaaaaaaa"
    repo_b = "repo_b-bbbbbbbb"

    idx_b_a = TemporalIndex(store, current_sha=_SHA_B)
    idx_b_a.upsert_node(
        _make_function_node(name="added_in_a", repo_id=repo_a, file_path="a/m.py")
    )
    idx_b_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b_b.upsert_node(
        _make_function_node(name="added_in_b", repo_id=repo_b, file_path="b/m.py")
    )
    store.close()

    only_a = diff_graph(
        repo_root=str(workspace),
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        repo=repo_a,
    )
    added_qns_a = [r["qualified_name"] for r in only_a["added"]]
    assert "a/m.py::added_in_a" in added_qns_a
    assert "b/m.py::added_in_b" not in added_qns_a


# ---------------------------------------------------------------------------
# (9) impact_radius respects as_of
# ---------------------------------------------------------------------------


def test_query_impact_respects_as_of(workspace: Path, store: GraphStore) -> None:
    """get_impact_radius(... as_of=sha) only walks rows valid at that sha.

    Insert a node + edge at sha_a. Supersede the node at sha_b. With
    as_of="" the seed file scan picks up the sha_b currently-valid row;
    with as_of=sha_a it picks up the sha_a historical row. We assert the
    impact response stays well-formed in both cases (the BFS is over
    qualified_names, which are shared across the two physical rows).
    """
    file_path = str(workspace / "src" / "m.py")
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(file_path).write_text("def retry():\n    return 1\n")

    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(
            file_path=file_path, source_text="def retry():\n    return 1\n"
        )
    )
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(
        _make_function_node(
            file_path=file_path, source_text="def retry():\n    return 2\n"
        )
    )
    store.close()

    default_result = get_impact_radius(
        changed_files=[file_path],
        repo_root=str(workspace),
        max_depth=1,
    )
    assert default_result["status"] == "ok"
    default_qns = [n["qualified_name"] for n in default_result["changed_nodes"]]
    # Currently-valid row should appear exactly once (no duplicates from the
    # closed-out historical row).
    assert default_qns.count(f"{file_path}::retry") == 1

    historical_result = get_impact_radius(
        changed_files=[file_path],
        repo_root=str(workspace),
        max_depth=1,
        as_of=_SHA_A,
    )
    assert historical_result["status"] == "ok"
    historical_qns = [n["qualified_name"] for n in historical_result["changed_nodes"]]
    assert historical_qns.count(f"{file_path}::retry") == 1


# ---------------------------------------------------------------------------
# (10) server.query dispatches the diff action
# ---------------------------------------------------------------------------


def test_server_query_diff_action_dispatches(
    workspace: Path, store: GraphStore
) -> None:
    """The MCP `query` tool with action='diff' returns the diff payload."""
    from better_code_review_graph.server import query as query_tool

    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(_make_function_node(name="brand_new"))
    store.close()

    raw = query_tool(
        action="diff",
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        repo_root=str(workspace),
    )
    payload = json.loads(raw)
    assert payload["from_sha"] == _SHA_A
    assert payload["to_sha"] == _SHA_B
    added_qns = [r["qualified_name"] for r in payload["added"]]
    assert "src/m.py::brand_new" in added_qns


# ---------------------------------------------------------------------------
# (11) Edges: added and removed
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# (11) Edges: added and removed
# ---------------------------------------------------------------------------


def test_diff_graph_returns_edge_changes(workspace: Path, store: GraphStore) -> None:
    """Edges added or closed at to_sha show up in the `edges` key."""
    from better_code_review_graph.graph import EdgeInfo

    # Edge 1: exists in A, closed in B
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    edge_removed = EdgeInfo(
        kind="CALLS",
        source="src/m.py::caller",
        target="src/m.py::callee_old",
        file_path="src/m.py",
        line=10,
    )
    idx_a.upsert_edge(edge_removed)

    # Manual close-out for edge_removed at SHA_B
    store._conn.execute(
        "UPDATE edges SET valid_to_sha = ? WHERE source_qualified = ?",
        (_SHA_B, "src/m.py::caller"),
    )

    # Edge 2: introduced in B
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    edge_added = EdgeInfo(
        kind="CALLS",
        source="src/m.py::caller",
        target="src/m.py::callee_new",
        file_path="src/m.py",
        line=12,
    )
    idx_b.upsert_edge(edge_added)
    store._conn.commit()
    store.close()

    result = diff_graph(repo_root=str(workspace), from_sha=_SHA_A, to_sha=_SHA_B)
    assert "edges" in result
    added = result["edges"]["added"]
    removed = result["edges"]["removed"]

    assert any(e["target_qualified"] == "src/m.py::callee_new" for e in added)
    assert any(e["target_qualified"] == "src/m.py::callee_old" for e in removed)
