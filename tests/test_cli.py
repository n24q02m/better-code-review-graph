"""Tests for the CLI module (cli.py) -- pure MCP server entry."""

from __future__ import annotations

from unittest.mock import patch

from better_code_review_graph.cli import main


class TestMainCLI:
    @patch("better_code_review_graph.cli.asyncio.run")
    def test_starts_server(self, mock_asyncio_run):
        with patch("better_code_review_graph.server.serve_main") as mock_serve:
            main()
            mock_serve.assert_called_once()
            mock_asyncio_run.assert_called_once()
