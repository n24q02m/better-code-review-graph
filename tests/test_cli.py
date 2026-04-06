"""Tests for the CLI module (cli.py) -- pure MCP server entry."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from better_code_review_graph.cli import main


class TestMainCLI:
    def test_starts_server(self):
        with (
            patch("better_code_review_graph.server.serve_main") as mock_serve,
            patch(
                "better_code_review_graph.relay_setup.ensure_config",
                new_callable=AsyncMock,
            ),
        ):
            main()
            mock_serve.assert_called_once()
