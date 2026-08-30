"""Phase 2 Task 10: cross-cutting ``repo`` query parameter.

Verifies that query/review tools accept a ``repo: str = ""`` kwarg that
filters results to the matching ``repo_id``. Default ``""`` returns
results across all repos (backwards-compatible).

Also covers the federated ``build_or_update_graph(roots=[...])`` path
that registers each root in the :class:`RepoRegistry` and parses files
under each, plus the legacy single-root path that must continue to work
unchanged when ``roots`` is omitted.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from better_code_review_graph.federation import RepoRegistry
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import (
    build_or_update_graph,
    get_impact_radius,
    get_review_context,
    query_graph,
    semantic_search_nodes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_two_repo_graph(store: GraphStore, repo_a_dir: Path, repo_b_dir: Path) -> None:
    """Seed a graph with two repos: repo_a and repo_b.

    Each has one File + one Function with the bare name ``retry`` (so a
    keyword search for "retry" hits both, and the ``repo`` filter is what
    discriminates).
    """
    repo_a_id = "repo_a-aaaaaaaa"
    repo_b_id = "repo_b-bbbbbbbb"

    file_a = str(repo_a_dir / "a.py")
    file_b = str(repo_b_dir / "b.py")

    store.upsert_node(
        NodeInfo(
            kind="File",
            name=file_a,
            file_path=file_a,
            line_start=1,
            line_end=5,
            language="python",
            repo_id=repo_a_id,
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="retry",
            file_path=file_a,
            line_start=1,
            line_end=3,
            language="python",
            repo_id=repo_a_id,
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=file_b,
            file_path=file_b,
            line_start=1,
            line_end=5,
            language="python",
            repo_id=repo_b_id,
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="retry",
            file_path=file_b,
            line_start=1,
            line_end=3,
            language="python",
            repo_id=repo_b_id,
        )
    )
    # CALLS edge inside repo_a so impact radius has something to traverse.
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="caller_a",
            file_path=file_a,
            line_start=4,
            line_end=5,
            language="python",
            repo_id=repo_a_id,
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source=f"{file_a}::caller_a",
            target=f"{file_a}::retry",
            file_path=file_a,
            line=4,
            repo_id=repo_a_id,
        )
    )
    # CALLS edge inside repo_b.
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="caller_b",
            file_path=file_b,
            line_start=4,
            line_end=5,
            language="python",
            repo_id=repo_b_id,
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source=f"{file_b}::caller_b",
            target=f"{file_b}::retry",
            file_path=file_b,
            line=4,
            repo_id=repo_b_id,
        )
    )
    store.commit()


@pytest.fixture
def two_repo_setup(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Build a workspace with two fake repo dirs + seeded graph DB.

    Returns a dict of ``{workspace, repo_a_dir, repo_b_dir, store, db_path,
    repo_a_id, repo_b_id}`` for tests to consume. Each repo dir gets a
    fake ``.git`` so ``_validate_repo_root`` accepts it as a project
    root.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    crg_dir = workspace / ".code-review-graph"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")

    repo_a_dir = workspace / "repo_a"
    repo_a_dir.mkdir()
    repo_b_dir = workspace / "repo_b"
    repo_b_dir.mkdir()

    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))
    _seed_two_repo_graph(store, repo_a_dir, repo_b_dir)

    yield {
        "workspace": workspace,
        "repo_a_dir": repo_a_dir,
        "repo_b_dir": repo_b_dir,
        "store": store,
        "db_path": db_path,
        "repo_a_id": "repo_a-aaaaaaaa",
        "repo_b_id": "repo_b-bbbbbbbb",
    }
    store.close()


# ---------------------------------------------------------------------------
# 1+2: query_graph repo filter on/off
# ---------------------------------------------------------------------------


def test_query_graph_repo_filter_returns_only_matching(
    two_repo_setup: dict[str, Any],
) -> None:
    """``query_graph(... repo='repo_a-...')`` returns only repo_a callers."""
    workspace = two_repo_setup["workspace"]
    repo_a_id = two_repo_setup["repo_a_id"]

    result = query_graph(
        pattern="callers_of",
        target="retry",
        repo_root=str(workspace),
        repo=repo_a_id,
    )

    assert result["status"] == "ok", result
    assert result["results"], "expected at least one caller in repo_a"
    for n in result["results"]:
        # caller_a is in repo_a/a.py; caller_b is in repo_b/b.py.
        assert "/repo_a/" in n["file_path"] or "\\repo_a\\" in n["file_path"], n


def test_query_graph_default_returns_all_repos(
    two_repo_setup: dict[str, Any],
) -> None:
    """No ``repo`` kwarg -> nodes from both repos visible via search.

    Uses semantic_search_nodes (no kind/repo filter) since ``callers_of``
    on a name shared across repos triggers the ambiguity heuristic
    instead of returning a flat list. Validates that the default
    behaviour ``repo == ""`` does not silently scope to a single repo.
    """
    workspace = two_repo_setup["workspace"]

    result = semantic_search_nodes(
        query="retry",
        repo_root=str(workspace),
    )

    assert result["status"] == "ok", result
    file_paths = {n["file_path"] for n in result["results"]}
    has_a = any("repo_a" in fp for fp in file_paths)
    has_b = any("repo_b" in fp for fp in file_paths)
    assert has_a and has_b, (
        f"expected matches from both repos; got file_paths={file_paths}"
    )


# ---------------------------------------------------------------------------
# 3: get_impact_radius repo filter
# ---------------------------------------------------------------------------


def test_get_impact_radius_repo_filter(
    two_repo_setup: dict[str, Any],
) -> None:
    """``get_impact_radius(... repo='repo_a-...')`` only returns repo_a nodes."""
    workspace = two_repo_setup["workspace"]
    repo_a_id = two_repo_setup["repo_a_id"]
    repo_a_dir = two_repo_setup["repo_a_dir"]

    # Pass changed_files explicitly so we don't need a real git diff.
    result = get_impact_radius(
        changed_files=[str(repo_a_dir / "a.py")],
        repo_root=str(workspace),
        repo=repo_a_id,
    )

    assert result["status"] == "ok", result
    # Every node in changed_nodes + impacted_nodes must live under repo_a.
    for node in result["changed_nodes"] + result["impacted_nodes"]:
        fp = node.get("file_path", "")
        assert "repo_a" in fp, f"unexpected repo in impact result: {fp!r}"
        assert "repo_b" not in fp, f"repo_b leaked into repo_a-filter: {fp!r}"


def test_impact_repo_filter_batches_typed_node_ids(
    two_repo_setup: dict[str, Any],
) -> None:
    store = two_repo_setup["store"]
    repo_a_id = two_repo_setup["repo_a_id"]
    repo_a_dir = two_repo_setup["repo_a_dir"]
    statements: list[str] = []
    store._conn.set_trace_callback(statements.append)
    try:
        result = store.get_impact_radius(
            [str(repo_a_dir / "a.py")],
            repo=repo_a_id,
        )
    finally:
        store._conn.set_trace_callback(None)

    assert result["changed_nodes"]
    typed_batch_queries = [
        statement
        for statement in statements
        if "ID IN (SELECT CAST(VALUE AS INTEGER) FROM JSON_EACH(" in statement.upper()
    ]
    assert len(typed_batch_queries) == 2
    assert not any(
        "SELECT REPO_ID FROM NODES WHERE ID =" in statement.upper()
        for statement in statements
    )


# ---------------------------------------------------------------------------
# 4: semantic_search_nodes repo filter (keyword fallback path)
# ---------------------------------------------------------------------------


def test_semantic_search_nodes_repo_filter(
    two_repo_setup: dict[str, Any],
) -> None:
    """``semantic_search_nodes`` filtered to repo_a returns repo_a only.

    The fixture has no embeddings so this exercises the keyword-fallback
    code path; both paths must honour the ``repo`` filter.
    """
    workspace = two_repo_setup["workspace"]
    repo_a_id = two_repo_setup["repo_a_id"]

    result = semantic_search_nodes(
        query="retry",
        repo_root=str(workspace),
        repo=repo_a_id,
    )

    assert result["status"] == "ok", result
    assert result["results"], "expected at least one match"
    for n in result["results"]:
        assert "repo_a" in n["file_path"], n


# ---------------------------------------------------------------------------
# 5: get_review_context repo filter
# ---------------------------------------------------------------------------


def test_get_review_context_repo_filter(
    two_repo_setup: dict[str, Any],
) -> None:
    """``get_review_context(... repo='repo_a-...')`` scopes subgraph to repo_a."""
    workspace = two_repo_setup["workspace"]
    repo_a_id = two_repo_setup["repo_a_id"]
    repo_a_dir = two_repo_setup["repo_a_dir"]

    # Simulate a changed file in repo_a.
    (repo_a_dir / "a.py").write_text("def retry():\n    pass\n")
    result = get_review_context(
        changed_files=[str(repo_a_dir / "a.py")],
        include_source=False,
        repo_root=str(workspace),
        repo=repo_a_id,
    )

    assert result["status"] == "ok", result
    ctx = result["context"]
    # Subgraph nodes must all be in repo_a.
    for node in ctx["graph"]["changed_nodes"] + ctx["graph"]["impacted_nodes"]:
        fp = node.get("file_path", "")
        assert "repo_b" not in fp, f"repo_b leaked into review context: {fp!r}"


# ---------------------------------------------------------------------------
# 6+7: build_or_update_graph(roots=...) and single-root backwards compat
# ---------------------------------------------------------------------------


def _make_real_repo(parent: Path, name: str) -> Path:
    """Create a real-looking repo dir with .git and a small Python file."""
    repo = parent / name
    repo.mkdir()
    (repo / ".git").mkdir()
    py = repo / "main.py"
    py.write_text("def retry():\n    return 1\n")
    return repo


def test_build_or_update_graph_with_multiple_roots(tmp_path: Path) -> None:
    """``roots=[a, b]`` registers both in RepoRegistry and parses both."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / ".code-review-graph").mkdir()

    repo_a = _make_real_repo(workspace, "repo_a")
    repo_b = _make_real_repo(workspace, "repo_b")

    result = build_or_update_graph(
        full_rebuild=True,
        repo_root=str(workspace),
        roots=[str(repo_a), str(repo_b)],
    )

    assert result["status"] == "ok", result

    # Verify the registry has both repos.
    db_path = workspace / ".code-review-graph" / "graph.db"
    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_paths = {entry.path.resolve() for entry in registry.entries()}
        assert repo_a.resolve() in repo_paths, repo_paths
        assert repo_b.resolve() in repo_paths, repo_paths
        assert len(repo_paths) >= 2, f"expected >=2 repos, got {repo_paths}"

        # Verify nodes from both repos exist with non-empty repo_id.
        rows = store._conn.execute(
            "SELECT DISTINCT repo_id FROM nodes WHERE repo_id != ''"
        ).fetchall()
        repo_ids = {r["repo_id"] for r in rows}
        assert len(repo_ids) >= 2, (
            f"expected nodes tagged with >=2 distinct repo_ids, got {repo_ids}"
        )
    finally:
        store.close()


def test_query_graph_repo_filter_drops_cross_repo_direct_hit(
    two_repo_setup: dict[str, Any],
) -> None:
    """Direct qualified-name lookup that hits a cross-repo node falls back.

    Pass the qualified name of repo_b's ``retry`` while filtering to
    repo_a. The direct-lookup branch in ``_resolve_query_target`` must
    discard the cross-repo match and let the search-by-name fallback
    pick repo_a's ``retry`` instead — exercising the repo guard at
    L803-809 in tools.py.
    """
    workspace = two_repo_setup["workspace"]
    repo_a_id = two_repo_setup["repo_a_id"]
    repo_b_dir = two_repo_setup["repo_b_dir"]

    cross_repo_qn = f"{repo_b_dir / 'b.py'}::retry"
    result = query_graph(
        pattern="callers_of",
        target=cross_repo_qn,
        repo_root=str(workspace),
        repo=repo_a_id,
    )

    # Either the resolver finds repo_a's retry via name fallback, or
    # returns not_found. Either way, no repo_b node may surface in the
    # result — that's the invariant the guard protects.
    if result["status"] == "ok":
        for n in result["results"]:
            assert "repo_b" not in n.get("file_path", ""), n


def test_build_or_update_graph_single_root_backwards_compat(tmp_path: Path) -> None:
    """Legacy single-root call (no ``roots`` kwarg) works unchanged."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / ".code-review-graph").mkdir()
    (workspace / "main.py").write_text("def retry():\n    return 1\n")

    result = build_or_update_graph(
        full_rebuild=True,
        repo_root=str(workspace),
    )

    assert result["status"] == "ok", result
    assert result.get("build_type") == "full"
    assert result.get("files_parsed", 0) >= 1
