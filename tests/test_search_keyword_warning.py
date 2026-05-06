"""Tests for #317: keyword-fallback warning at search time.

When embeddings_count=0 AND the query is not a literal identifier (contains
spaces, punctuation, etc.) the search response should include a warning so
agents don't silently trust keyword-substring matches as semantic results.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import (
    _looks_like_literal_identifier,
    semantic_search_nodes,
)


@pytest.mark.parametrize(
    "query, is_literal",
    [
        ("foo", True),
        ("foo_bar", True),
        ("FooBar", True),
        ("foo.bar", True),
        ("foo::bar", True),
        ("foo-bar", True),
        ("src/foo.py", True),
        ("how does authentication work", False),
        ("firebase auth", False),
        ("what is the impact?", False),
        ("foo bar", False),
        ("foo, bar", False),
    ],
)
def test_looks_like_literal_identifier(query, is_literal):
    assert _looks_like_literal_identifier(query) is is_literal


@pytest.fixture
def repo_with_graph(tmp_path):
    (tmp_path / ".git").mkdir()
    crg = tmp_path / ".code-review-graph"
    crg.mkdir()
    (crg / ".gitignore").write_text("*\n")
    db = crg / "graph.db"
    store = GraphStore(str(db))
    abs_path = str(tmp_path / "auth.py")
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="login",
            file_path=abs_path,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.commit()
    store.close()
    return tmp_path


def test_warning_emitted_for_phrase_query_no_embeddings(repo_with_graph):
    result = semantic_search_nodes(
        query="how does login work", repo_root=str(repo_with_graph)
    )
    assert result["status"] == "ok"
    assert result["search_mode"] == "keyword"
    assert "warning" in result
    assert "keyword-substring" in result["warning"]


def test_no_warning_for_literal_identifier_no_embeddings(repo_with_graph):
    result = semantic_search_nodes(query="login", repo_root=str(repo_with_graph))
    assert result["status"] == "ok"
    assert result["search_mode"] == "keyword"
    assert "warning" not in result
