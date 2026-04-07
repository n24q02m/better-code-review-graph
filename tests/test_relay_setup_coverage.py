from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from better_code_review_graph.relay_setup import (
    CLOUD_KEYS,
    ensure_config,
)


@pytest.mark.asyncio
async def test_ensure_config_read_config_exception(monkeypatch):
    """Test 1: Mock read_config to raise an Exception and verify ensure_config continues."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    # Mock read_config to raise an exception
    with patch(
        "mcp_relay_core.storage.config_file.read_config",
        side_effect=Exception("Read error"),
    ):
        # Mock create_session to return None to avoid actual relay setup
        with patch(
            "mcp_relay_core.relay.client.create_session",
            new_callable=AsyncMock,
            side_effect=Exception("No relay"),
        ):
            result = await ensure_config()
            assert result is None


@pytest.mark.asyncio
async def test_ensure_config_httpx_post_exception(monkeypatch):
    """Test 2: Mock httpx.AsyncClient.post to raise an Exception and verify ensure_config continues."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("mcp_relay_core.storage.config_file.read_config", return_value=None):
        mock_session = MagicMock()
        mock_session.relay_url = "https://relay.example.com/setup#k=abc"
        mock_session.session_id = "test-session"

        with (
            patch(
                "mcp_relay_core.relay.client.create_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                return_value={"GEMINI_API_KEY": "from-relay"},
            ),
            patch("mcp_relay_core.storage.config_file.write_config"),
            patch("httpx.AsyncClient") as mock_http_client,
        ):
            mock_client_instance = mock_http_client.return_value.__aenter__.return_value
            mock_client_instance.post.side_effect = Exception("HTTP error")

            result = await ensure_config()
            assert result == {"GEMINI_API_KEY": "from-relay"}
            assert os.environ.get("GEMINI_API_KEY") == "from-relay"
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_ensure_config_poll_runtime_error_unexpected(monkeypatch):
    """Test 3: Mock poll_for_result to raise a RuntimeError("Unexpected error") and verify logger.debug."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("mcp_relay_core.storage.config_file.read_config", return_value=None):
        mock_session = MagicMock()
        mock_session.relay_url = "https://relay.example.com/setup#k=abc"

        with (
            patch(
                "mcp_relay_core.relay.client.create_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Unexpected error"),
            ),
            patch("better_code_review_graph.relay_setup.logger") as mock_logger,
        ):
            result = await ensure_config()
            assert result is None
            # Check that debug was called with the RuntimeError
            args, _ = mock_logger.debug.call_args
            assert args[0] == "Relay setup ended: %s"
            assert isinstance(args[1], RuntimeError)
            assert str(args[1]) == "Unexpected error"
