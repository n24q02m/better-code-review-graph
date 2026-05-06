"""Tests for #316: auto-resolve File+Function ambiguity for call-graph queries.

When ``callers_of`` / ``callees_of`` matches both a File node AND a
Function node with the same bare name, the Function is the only sensible
target for call-graph questions. Auto-pick instead of returning ambiguous.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import query_graph


@pytest.fixture
def repo_with_collision(tmp_path):
    """Repo with `auth.py` File and `auth` Function colliding by name."""
    (tmp_path / ".git").mkdir()
    crg = tmp_path / ".code-review-graph"
    crg.mkdir()
    (crg / ".gitignore").write_text("*\n")
    db = crg / "graph.db"
    store = GraphStore(str(db))

    # Module-level `auth.py` File node + `auth()` Function node + a caller.
    abs_auth = str(tmp_path / "auth.py")
    abs_main = str(tmp_path / "main.py")
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_auth,
            file_path=abs_auth,
            line_start=1,
            line_end=10,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="auth",
            file_path=abs_auth,
            line_start=2,
            line_end=4,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_main,
            file_path=abs_main,
            line_start=1,
            line_end=5,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="login",
            file_path=abs_main,
            line_start=2,
            line_end=4,
            language="python",
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source=f"{abs_main}::login",
            target=f"{abs_auth}::auth",
            file_path=abs_main,
            line=3,
        )
    )
    store.commit()
    store.close()
    return tmp_path


def test_callers_of_auto_picks_function_over_file(repo_with_collision):
    """`callers_of auth` should auto-pick the Function and find the caller."""
    result = query_graph(
        pattern="callers_of", target="auth", repo_root=str(repo_with_collision)
    )
    assert result["status"] == "ok"
    # The Function caller `login` should be returned.
    qns = {r["qualified_name"] for r in result["results"]}
    assert any(qn.endswith("::login") for qn in qns), result


def test_callees_of_auto_picks_function_over_file(repo_with_collision):
    """`callees_of auth` should auto-pick the Function (no callees in fixture)."""
    result = query_graph(
        pattern="callees_of", target="auth", repo_root=str(repo_with_collision)
    )
    assert result["status"] == "ok"


def test_other_patterns_still_ambiguous(repo_with_collision):
    """`children_of auth` / `file_summary` keep the existing ambiguity behavior --
    File may legitimately be what was wanted there."""
    result = query_graph(
        pattern="children_of", target="auth", repo_root=str(repo_with_collision)
    )
    assert result["status"] == "ambiguous"
    assert result["reason"] == "ambiguous_unqualified"
