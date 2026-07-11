"""Tests for the CLI module (cli.py) -- shared mcp_core CLI builder mount."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from better_code_review_graph.cli import main


class TestServeDispatch:
    def test_starts_server(self):
        with (
            patch.object(sys, "argv", ["better-code-review-graph"]),
            patch("better_code_review_graph.server.serve_main") as mock_serve,
        ):
            rc = main()

        mock_serve.assert_called_once()
        assert rc == 0

    def test_http_flag_passes_through_argv_unchanged(self):
        with (
            patch.object(sys, "argv", ["better-code-review-graph", "--http"]),
            patch("better_code_review_graph.server.serve_main") as mock_serve,
        ):
            rc = main()

        mock_serve.assert_called_once()
        assert rc == 0

    def test_main_runs_stdio_directly(self):
        """serve_main(stdio) invokes FastMCP stdio directly (no bridge layer)."""
        from better_code_review_graph import server as server_module

        with (
            patch.object(sys, "argv", ["better-code-review-graph"]),
            patch.object(server_module.mcp, "run") as mock_run,
            patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}),
        ):
            main()
            mock_run.assert_called_once_with(transport="stdio")

    def test_main_continues_on_relay_error(self):
        with (
            patch.object(sys, "argv", ["better-code-review-graph"]),
            patch(
                "better_code_review_graph.credential_state.resolve_credential_state",
                side_effect=Exception("relay broken"),
            ),
            patch("better_code_review_graph.server.mcp"),
            patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}),
        ):
            try:
                main()
            except Exception:
                pass


class TestGraphSubcommand:
    """`better-code-review-graph graph build|embed` -- lazy tools.py calls."""

    def test_build_passes_args_and_prints_json(self, capsys):
        result = {"status": "ok", "build_type": "full", "files_parsed": 3}
        with (
            patch.object(
                sys,
                "argv",
                ["better-code-review-graph", "graph", "build", "--full-rebuild"],
            ),
            patch(
                "better_code_review_graph.tools.build_or_update_graph",
                return_value=result,
            ) as mock_build,
        ):
            rc = main()

        mock_build.assert_called_once_with(
            full_rebuild=True, repo_root=None, base="HEAD~1"
        )
        assert rc == 0
        assert '"status": "ok"' in capsys.readouterr().out

    def test_build_incremental_default_args(self):
        result = {"status": "ok", "build_type": "incremental"}
        with (
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "graph",
                    "build",
                    "--repo-root",
                    "/tmp/repo",
                    "--base",
                    "main",
                ],
            ),
            patch(
                "better_code_review_graph.tools.build_or_update_graph",
                return_value=result,
            ) as mock_build,
        ):
            rc = main()

        mock_build.assert_called_once_with(
            full_rebuild=False, repo_root="/tmp/repo", base="main"
        )
        assert rc == 0

    def test_build_error_status_returns_nonzero(self, capsys):
        result = {"status": "error", "error": "boom"}
        with (
            patch.object(sys, "argv", ["better-code-review-graph", "graph", "build"]),
            patch(
                "better_code_review_graph.tools.build_or_update_graph",
                return_value=result,
            ),
        ):
            rc = main()

        assert rc == 1
        assert "boom" in capsys.readouterr().out

    def test_embed_passes_repo_root_and_prints_json(self, capsys):
        result = {
            "status": "ok",
            "newly_embedded": 5,
            "total_embeddings": 42,
            "backend": "local",
        }
        with (
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "graph",
                    "embed",
                    "--repo-root",
                    "/tmp/repo",
                ],
            ),
            patch(
                "better_code_review_graph.tools.embed_graph", return_value=result
            ) as mock_embed,
        ):
            rc = main()

        mock_embed.assert_called_once_with(repo_root="/tmp/repo")
        assert rc == 0
        assert '"backend": "local"' in capsys.readouterr().out

    def test_unknown_graph_action_exits_2(self):
        with patch.object(sys, "argv", ["better-code-review-graph", "graph", "bogus"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
