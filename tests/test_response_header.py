"""Tests for #330: response header (embeddings_count + keyword_only).

Every ``search`` and ``query`` ok-response should include a ``header`` block
so consumers can record search mode (semantic vs keyword) without making a
separate ``config status`` call.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import (
    _build_response_header,
    query_graph,
    semantic_search_nodes,
)


@pytest.fixture
def repo_with_graph(tmp_path):
    """Minimal repo + graph fixture for header tests."""
    (tmp_path / ".git").mkdir()
    crg_dir = tmp_path / ".code-review-graph"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")

    auth_py = tmp_path / "auth.py"
    auth_py.write_text("def login():\n    pass\n")

    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))
    abs_auth = str(auth_py)
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_auth,
            file_path=abs_auth,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="login",
            file_path=abs_auth,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CONTAINS",
            source=abs_auth,
            target=f"{abs_auth}::login",
            file_path=abs_auth,
        )
    )
    store.set_metadata("last_updated", "2026-04-29T10:00:00")
    store.commit()
    store.close()
    return tmp_path


def test_query_response_includes_header(repo_with_graph):
    abs_auth = str(repo_with_graph / "auth.py")
    result = query_graph(
        pattern="callers_of",
        target=f"{abs_auth}::login",
        repo_root=str(repo_with_graph),
    )
    assert result["status"] == "ok"
    header = result["header"]
    assert "embeddings_count" in header
    assert "keyword_only" in header
    assert "graph_last_updated" in header
    # No embeddings have been computed; keyword_only must be True.
    assert header["embeddings_count"] == 0
    assert header["keyword_only"] is True
    assert header["graph_last_updated"] == "2026-04-29T10:00:00"


def test_search_keyword_response_includes_header(repo_with_graph):
    """search with no embeddings -> keyword_only=True."""
    result = semantic_search_nodes(query="login", repo_root=str(repo_with_graph))
    assert result["status"] == "ok"
    header = result["header"]
    assert header["embeddings_count"] == 0
    assert header["keyword_only"] is True


def test_build_response_header_no_store():
    """Helper degrades gracefully when store/db_path are unavailable."""
    h = _build_response_header(None, None)
    assert h["embeddings_count"] == 0
    assert h["keyword_only"] is True
    assert h["graph_last_updated"] is None
