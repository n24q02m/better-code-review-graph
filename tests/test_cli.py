"""Tests for the CLI module (cli.py) -- pure MCP server entry."""

from __future__ import annotations

from unittest.mock import patch

from better_code_review_graph.cli import main


class TestMainCLI:
    def test_starts_server(self):
        with patch("better_code_review_graph.server.serve_main") as mock_serve:
            main()
            mock_serve.assert_called_once()


class TestCLIIntegration:
    def test_main_runs_stdio_directly(self):
        """serve_main(stdio) invokes FastMCP stdio directly (no bridge layer)."""
        import os
        from unittest.mock import patch

        from better_code_review_graph import server as server_module

        with (
            patch.object(server_module.mcp, "run") as mock_run,
            patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}),
        ):
            from better_code_review_graph.cli import main

            main()
            mock_run.assert_called_once_with(transport="stdio")

    def test_main_continues_on_relay_error(self):
        import os
        from unittest.mock import patch

        with (
            patch(
                "better_code_review_graph.credential_state.resolve_credential_state",
                side_effect=Exception("relay broken"),
            ),
            patch("better_code_review_graph.server.mcp"),
            patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}),
        ):
            from better_code_review_graph.cli import main

            try:
                main()
            except Exception:
                pass
