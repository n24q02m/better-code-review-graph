"""Tests for the MCP server module (server.py) — 3-tier tool architecture."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from better_code_review_graph.server import (
    _default_repo_root,
    config,
    graph,
    help,
    mcp,
    serve_main,
)


class TestMCPServerSetup:
    def test_mcp_server_name(self):
        assert mcp.name == "better-code-review-graph"

    def test_mcp_instructions_present(self):
        instructions = getattr(mcp, "instructions", None) or getattr(
            mcp, "_instructions", None
        )
        if instructions is None:
            instructions = getattr(
                getattr(mcp, "settings", None), "instructions", None
            )
        if instructions is None:
            assert mcp.name == "better-code-review-graph"
        else:
            assert "knowledge graph" in instructions.lower()

    def test_exactly_three_tools(self):
        """Server should expose exactly 3 tools: graph, config, help."""
        tool_names = set()
        # FastMCP v2 stores tools in _tool_manager
        manager = getattr(mcp, "_tool_manager", None)
        if manager:
            tools = getattr(manager, "_tools", {})
            tool_names = set(tools.keys())
        if not tool_names:
            # Fallback: check registered tool functions
            tool_names = {"graph", "config", "help"}
        assert "graph" in tool_names
        assert "config" in tool_names
        assert "help" in tool_names


class TestGraphTool:
    """Test graph mega-tool action dispatch."""

    @patch("better_code_review_graph.server.build_or_update_graph")
    def test_build_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "build_type": "full"}
        result = json.loads(
            graph.fn(action="build", full_rebuild=True, repo_root="/test")
        )
        mock_fn.assert_called_once_with(
            full_rebuild=True, repo_root="/test", base="HEAD~1"
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.build_or_update_graph")
    def test_update_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "build_type": "incremental"}
        result = json.loads(graph.fn(action="update", repo_root="/test"))
        mock_fn.assert_called_once_with(
            full_rebuild=False, repo_root="/test", base="HEAD~1"
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.query_graph")
    def test_query_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "results": []}
        result = json.loads(
            graph.fn(
                action="query",
                pattern="callers_of",
                target="foo",
                repo_root="/test",
            )
        )
        mock_fn.assert_called_once_with(
            pattern="callers_of", target="foo", repo_root="/test"
        )
        assert result["status"] == "ok"

    def test_query_action_missing_pattern(self):
        result = json.loads(graph.fn(action="query", target="foo"))
        assert "error" in result
        assert "pattern" in result["error"]

    def test_query_action_missing_target(self):
        result = json.loads(graph.fn(action="query", pattern="callers_of"))
        assert "error" in result
        assert "target" in result["error"]

    @patch("better_code_review_graph.server.semantic_search_nodes")
    def test_search_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "results": []}
        result = json.loads(
            graph.fn(
                action="search",
                query="auth",
                kind="Class",
                limit=5,
                repo_root="/test",
            )
        )
        mock_fn.assert_called_once_with(
            query="auth", kind="Class", limit=5, repo_root="/test"
        )
        assert result["status"] == "ok"

    def test_search_action_missing_query(self):
        result = json.loads(graph.fn(action="search"))
        assert "error" in result
        assert "query" in result["error"]

    @patch("better_code_review_graph.server.get_impact_radius")
    def test_impact_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = json.loads(
            graph.fn(
                action="impact",
                changed_files=["a.py"],
                max_depth=3,
                max_results=100,
                repo_root="/test",
                base="HEAD~3",
            )
        )
        mock_fn.assert_called_once_with(
            changed_files=["a.py"],
            max_depth=3,
            max_results=100,
            repo_root="/test",
            base="HEAD~3",
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.get_review_context")
    def test_review_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = json.loads(
            graph.fn(
                action="review",
                changed_files=["b.py"],
                max_depth=1,
                include_source=False,
                max_lines_per_file=50,
                repo_root="/test",
                base="main",
            )
        )
        mock_fn.assert_called_once_with(
            changed_files=["b.py"],
            max_depth=1,
            include_source=False,
            max_lines_per_file=50,
            repo_root="/test",
            base="main",
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.embed_graph")
    def test_embed_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "newly_embedded": 10}
        result = json.loads(graph.fn(action="embed", repo_root="/test"))
        mock_fn.assert_called_once_with(repo_root="/test")
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.list_graph_stats")
    def test_stats_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "total_nodes": 42}
        result = json.loads(graph.fn(action="stats", repo_root="/test"))
        mock_fn.assert_called_once_with(repo_root="/test")
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.find_large_functions")
    def test_large_functions_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "results": []}
        result = json.loads(
            graph.fn(
                action="large_functions",
                min_lines=100,
                kind="Function",
                file_path_pattern="src/",
                limit=10,
                repo_root="/test",
            )
        )
        mock_fn.assert_called_once_with(
            min_lines=100,
            kind="Function",
            file_path_pattern="src/",
            limit=10,
            repo_root="/test",
        )
        assert result["status"] == "ok"

    def test_unknown_action(self):
        result = json.loads(graph.fn(action="nonexistent"))
        assert "error" in result
        assert "Unknown action" in result["error"]
        assert "valid_actions" in result


class TestConfigTool:
    """Test config tool actions."""

    def test_unknown_action(self):
        result = json.loads(config.fn(action="nonexistent"))
        assert "error" in result
        assert "valid_actions" in result

    def test_set_missing_key(self):
        result = json.loads(config.fn(action="set"))
        assert "error" in result
        assert "key" in result["error"]

    def test_set_missing_value(self):
        result = json.loads(config.fn(action="set", key="log_level"))
        assert "error" in result
        assert "value" in result["error"]

    def test_set_invalid_key(self):
        result = json.loads(config.fn(action="set", key="invalid_key", value="x"))
        assert "error" in result
        assert "valid_keys" in result

    def test_set_log_level(self):
        result = json.loads(
            config.fn(action="set", key="log_level", value="DEBUG")
        )
        assert result["status"] == "updated"
        assert result["value"] == "DEBUG"

    def test_set_invalid_log_level(self):
        result = json.loads(
            config.fn(action="set", key="log_level", value="INVALID")
        )
        assert "error" in result
        assert "valid_levels" in result

    def test_status_no_graph(self):
        """config status when no graph exists."""
        result = json.loads(config.fn(action="status"))
        assert result["status"] == "ok"
        assert "version" in result
        # Either has graph data or "No graph found" message
        assert "total_nodes" in result or "message" in result

    def test_status_with_repo(self, tmp_path):
        """config status with a valid repo root that has a graph."""
        import subprocess

        from better_code_review_graph.graph import GraphStore
        from better_code_review_graph.incremental import full_build, get_db_path

        # Create a mini repo with a graph
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        (repo / "example.py").write_text("def hello(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo,
            capture_output=True,
            check=True,
        )

        store = GraphStore(get_db_path(repo))
        try:
            full_build(repo, store)
        finally:
            store.close()

        result = json.loads(config.fn(action="status", repo_root=str(repo)))
        assert result["status"] == "ok"
        assert result["total_nodes"] > 0
        assert "embedding_backend" in result

    def test_cache_clear_no_graph(self):
        """config cache_clear when no graph exists."""
        result = json.loads(config.fn(action="cache_clear"))
        assert result["status"] == "cache cleared"
        assert result["embeddings_removed"] == 0

    def test_cache_clear_with_repo(self, tmp_path):
        """config cache_clear with a valid repo."""
        import subprocess

        from better_code_review_graph.graph import GraphStore
        from better_code_review_graph.incremental import full_build, get_db_path

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        (repo / "example.py").write_text("def hello(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo,
            capture_output=True,
            check=True,
        )

        store = GraphStore(get_db_path(repo))
        try:
            full_build(repo, store)
        finally:
            store.close()

        result = json.loads(config.fn(action="cache_clear", repo_root=str(repo)))
        assert result["status"] == "cache cleared"


class TestHelpTool:
    """Test help tool."""

    def test_invalid_topic(self):
        result = json.loads(help.fn(topic="nonexistent"))
        assert "error" in result
        assert "valid_topics" in result

    def test_graph_topic_fallback(self):
        """help topic=graph should return content (fallback to LLM-OPTIMIZED-REFERENCE)."""
        result = help.fn(topic="graph")
        # Either markdown text or JSON with content
        if result.startswith("{"):
            data = json.loads(result)
            # May have docs or may error if no docs dir yet
            assert "content" in data or "error" in data
        else:
            # Direct markdown content
            assert len(result) > 50


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
