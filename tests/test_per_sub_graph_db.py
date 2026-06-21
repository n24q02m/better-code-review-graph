"""Per-JWT-sub graph DB isolation in HTTP multi-user mode.

The credential + model-chain dispatch became per-sub in #741, but the
graph DB itself was still resolved to ``<repo_root>/.code-review-graph/graph.db``
regardless of the bound sub -- so every concurrent JWT sub in a single
multi-user deployment shared ONE graph.db (user A could read user B's
code-graph nodes/edges/summaries).

These tests pin the contract that ``get_db_path``:

* returns the per-sub path (``<CRG_DATA_DIR>/subs/<sub>/graph.db``) when a
  JWT sub is bound (multi-user remote mode), distinct per sub; and
* falls back to the repo-relative path when no sub is bound
  (stdio / single-user HTTP), leaving that path byte-for-byte unchanged.

They exercise the contextvar plumbing directly (no full HTTP boot), the
same way ``test_multi_user.py`` does.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.credential_state import _current_sub
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.incremental import get_db_path
from better_code_review_graph.parser import NodeInfo


@pytest.fixture(autouse=True)
def _reset_contextvar():
    """Ensure each test starts with no active sub binding."""
    token = _current_sub.set(None)
    try:
        yield
    finally:
        _current_sub.reset(token)


def _node(name: str) -> NodeInfo:
    return NodeInfo(
        kind="Function",
        name=name,
        file_path="mod.py",
        line_start=1,
        line_end=2,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        modifiers=None,
        is_test=False,
    )


def test_stdio_no_sub_uses_repo_relative_path(tmp_path, monkeypatch):
    """No sub bound (stdio / single-user) -> ``<repo>/.code-review-graph/graph.db``."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()

    from better_code_review_graph.credential_state import set_current_sub

    set_current_sub(None)
    path = get_db_path(repo)
    assert path == repo / ".code-review-graph" / "graph.db"


def test_bound_sub_uses_per_sub_path(tmp_path, monkeypatch):
    """A bound JWT sub -> ``<CRG_DATA_DIR>/subs/<sub>/graph.db`` (not repo-relative)."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()

    from better_code_review_graph.credential_state import (
        db_path_for_sub,
        set_current_sub,
    )

    set_current_sub("user-a")
    path = get_db_path(repo)
    assert path == db_path_for_sub("user-a")
    # The analyzed-repo path must NOT be used for a bound sub.
    assert path != repo / ".code-review-graph" / "graph.db"
    assert "user-a" in str(path)


def test_two_subs_get_distinct_db_paths(tmp_path, monkeypatch):
    """Two different subs resolve to two different DB files."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()

    from better_code_review_graph.credential_state import set_current_sub

    set_current_sub("user-a")
    pa = get_db_path(repo)
    set_current_sub("user-b")
    pb = get_db_path(repo)

    assert pa != pb
    assert "user-a" in str(pa)
    assert "user-b" in str(pb)


def test_sub_b_query_does_not_see_sub_a_nodes(tmp_path, monkeypatch):
    """End-to-end isolation: sub A's written node is invisible to sub B.

    Opens the live store-open path (``get_db_path`` -> ``GraphStore``) once
    per sub, mirroring how each per-tool-call request resolves its store,
    and asserts the second sub's search returns nothing.
    """
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()

    from better_code_review_graph.credential_state import set_current_sub

    # sub A writes a node into its own graph DB.
    set_current_sub("user-a")
    store_a = GraphStore(get_db_path(repo))
    try:
        store_a.upsert_node(_node("secret_fn_of_a"))
        store_a.commit()
        assert store_a.search_nodes("secret_fn_of_a")
    finally:
        store_a.close()

    # sub B opens its store the same way and must NOT see sub A's node.
    set_current_sub("user-b")
    store_b = GraphStore(get_db_path(repo))
    try:
        assert store_b.search_nodes("secret_fn_of_a") == []
    finally:
        store_b.close()
