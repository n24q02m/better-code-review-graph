"""Tests for #318: spot_check action returns N random callsite snippets.

After a callers_of / callees_of / inheritors_of / importers_of query,
``spot_check(n=3)`` should return source snippets at 3 random callsites
from that result without re-running the query.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import (
    _LAST_CALLERS_RESULT,
    query_graph,
    spot_check_last_callers,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the per-repo last-result cache between tests."""
    _LAST_CALLERS_RESULT.clear()
    yield
    _LAST_CALLERS_RESULT.clear()


@pytest.fixture
def repo_with_callers(tmp_path):
    """Repo where 5 callers reference one Function across multiple files."""
    (tmp_path / ".git").mkdir()
    crg = tmp_path / ".code-review-graph"
    crg.mkdir()
    (crg / ".gitignore").write_text("*\n")

    # Target function
    target_py = tmp_path / "target.py"
    target_py.write_text("def fn():\n    return 1\n")
    abs_target = str(target_py)

    # 5 callers, each in its own file
    callers: list[str] = []
    for i in range(5):
        p = tmp_path / f"caller_{i}.py"
        p.write_text(f"from target import fn\n\n\ndef use_fn_{i}():\n    return fn()\n")
        callers.append(str(p))

    db = crg / "graph.db"
    store = GraphStore(str(db))
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_target,
            file_path=abs_target,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="fn",
            file_path=abs_target,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    for i, fp in enumerate(callers):
        store.upsert_node(
            NodeInfo(
                kind="File",
                name=fp,
                file_path=fp,
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name=f"use_fn_{i}",
                file_path=fp,
                line_start=4,
                line_end=5,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source=f"{fp}::use_fn_{i}",
                target=f"{abs_target}::fn",
                file_path=fp,
                line=5,
            )
        )
    store.commit()
    store.close()
    return tmp_path, abs_target


def test_spot_check_returns_samples_after_callers_of(repo_with_callers):
    repo, abs_target = repo_with_callers

    # Run callers_of first to populate the cache.
    result = query_graph(
        pattern="callers_of",
        target=f"{abs_target}::fn",
        repo_root=str(repo),
    )
    assert result["status"] == "ok"

    # Now spot_check should return 3 sampled callsite snippets.
    spot = spot_check_last_callers(n=3, repo_root=str(repo))
    assert spot["status"] == "ok"
    assert spot["pattern"] == "callers_of"
    assert len(spot["samples"]) == 3
    for s in spot["samples"]:
        assert s["file"]
        assert s["line"] > 0
        # snippet should contain the line number prefix from the source.
        assert "fn" in s["snippet"] or "use_fn" in s["snippet"]


def test_spot_check_no_cache_returns_no_cache_status(repo_with_callers):
    repo, _ = repo_with_callers
    spot = spot_check_last_callers(n=3, repo_root=str(repo))
    assert spot["status"] == "no_cache"
    assert spot["samples"] == []


def test_spot_check_n_clamped_to_available_edges(repo_with_callers):
    repo, abs_target = repo_with_callers
    query_graph(
        pattern="callers_of",
        target=f"{abs_target}::fn",
        repo_root=str(repo),
    )
    spot = spot_check_last_callers(n=99, repo_root=str(repo))
    assert spot["status"] == "ok"
    # 5 callers in fixture; n=99 clamps to 5.
    assert len(spot["samples"]) == 5
