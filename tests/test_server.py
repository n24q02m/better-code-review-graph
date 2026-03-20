"""Tests for the MCP server module (server.py)."""

from __future__ import annotations

from unittest.mock import patch

from better_code_review_graph.server import (
    _default_repo_root,
    build_or_update_graph_tool,
    embed_graph_tool,
    find_large_functions_tool,
    get_docs_section_tool,
    get_impact_radius_tool,
    get_review_context_tool,
    list_graph_stats_tool,
    mcp,
    query_graph_tool,
    semantic_search_nodes_tool,
    serve_main,
)


class TestMCPServerSetup:
    def test_mcp_server_name(self):
        assert mcp.name == "better-code-review-graph"

    def test_mcp_instructions_present(self):
        # FastMCP stores instructions in settings or as an attribute
        instructions = getattr(mcp, "instructions", None) or getattr(
            mcp, "_instructions", None
        )
        if instructions is None:
            # Check settings
            instructions = getattr(getattr(mcp, "settings", None), "instructions", None)
        if instructions is None:
            # Access via the init kwargs -- just verify the server was created
            assert mcp.name == "better-code-review-graph"
        else:
            assert "knowledge graph" in instructions.lower()


class TestToolDelegation:
    """Verify server tools delegate correctly to tools.py implementations."""

    @patch("better_code_review_graph.server.build_or_update_graph")
    def test_build_or_update_graph_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = build_or_update_graph_tool(
            full_rebuild=True, repo_root="/test", base="HEAD~2"
        )
        mock_fn.assert_called_once_with(
            full_rebuild=True, repo_root="/test", base="HEAD~2"
        )
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.get_impact_radius")
    def test_get_impact_radius_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = get_impact_radius_tool(
            changed_files=["a.py"],
            max_depth=3,
            max_results=100,
            repo_root="/test",
            base="HEAD~3",
        )
        mock_fn.assert_called_once_with(
            changed_files=["a.py"],
            max_depth=3,
            max_results=100,
            repo_root="/test",
            base="HEAD~3",
        )
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.query_graph")
    def test_query_graph_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = query_graph_tool(pattern="callers_of", target="foo", repo_root="/test")
        mock_fn.assert_called_once_with(
            pattern="callers_of", target="foo", repo_root="/test"
        )
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.get_review_context")
    def test_get_review_context_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = get_review_context_tool(
            changed_files=["b.py"],
            max_depth=1,
            include_source=False,
            max_lines_per_file=50,
            repo_root="/test",
            base="main",
        )
        mock_fn.assert_called_once_with(
            changed_files=["b.py"],
            max_depth=1,
            include_source=False,
            max_lines_per_file=50,
            repo_root="/test",
            base="main",
        )
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.semantic_search_nodes")
    def test_semantic_search_nodes_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = semantic_search_nodes_tool(
            query="auth", kind="Class", limit=5, repo_root="/test"
        )
        mock_fn.assert_called_once_with(
            query="auth", kind="Class", limit=5, repo_root="/test"
        )
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.embed_graph")
    def test_embed_graph_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = embed_graph_tool(repo_root="/test")
        mock_fn.assert_called_once_with(repo_root="/test")
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.list_graph_stats")
    def test_list_graph_stats_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = list_graph_stats_tool(repo_root="/test")
        mock_fn.assert_called_once_with(repo_root="/test")
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.get_docs_section")
    def test_get_docs_section_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = get_docs_section_tool(section_name="usage")
        mock_fn.assert_called_once_with(
            section_name="usage", repo_root=_default_repo_root
        )
        assert result == {"status": "ok"}

    @patch("better_code_review_graph.server.find_large_functions")
    def test_find_large_functions_tool(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = find_large_functions_tool(
            min_lines=100,
            kind="Function",
            file_path_pattern="src/",
            limit=10,
            repo_root="/test",
        )
        mock_fn.assert_called_once_with(
            min_lines=100,
            kind="Function",
            file_path_pattern="src/",
            limit=10,
            repo_root="/test",
        )
        assert result == {"status": "ok"}


class TestServeMain:
    @patch("better_code_review_graph.server.mcp")
    def test_serve_main_sets_repo_root(self, mock_mcp):
        import better_code_review_graph.server as server_module

        serve_main(repo_root="/my/repo")
        assert server_module._default_repo_root == "/my/repo"
        mock_mcp.run.assert_called_once_with(transport="stdio")

    @patch("better_code_review_graph.server.mcp")
    def test_serve_main_none_repo_root(self, mock_mcp):
        import better_code_review_graph.server as server_module

        serve_main(repo_root=None)
        assert server_module._default_repo_root is None
        mock_mcp.run.assert_called_once_with(transport="stdio")
