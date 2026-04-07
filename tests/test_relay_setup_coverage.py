import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from better_code_review_graph.relay_setup import (
    CLOUD_KEYS,
    ensure_config,
)


@pytest.mark.asyncio
async def test_ensure_config_read_config_exception(monkeypatch):
    """Test that ensure_config handles Exception in read_config and continues."""
    # Ensure no cloud keys in env
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch(
        "mcp_relay_core.storage.config_file.read_config",
        side_effect=Exception("Read config failed"),
    ):
        # Mock create_session to fail so we don't actually start a relay session
        with patch(
            "mcp_relay_core.relay.client.create_session",
            side_effect=Exception("No relay"),
        ):
            result = await ensure_config()
            assert result is None
            # If it reached here, it means it survived the read_config exception


@pytest.mark.asyncio
async def test_ensure_config_create_session_exception(monkeypatch):
    """Test that ensure_config handles Exception in create_session and returns None."""
    # Ensure no cloud keys in env
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("mcp_relay_core.storage.config_file.read_config", return_value=None):
        with patch(
            "mcp_relay_core.relay.client.create_session",
            side_effect=Exception("Create session failed"),
        ):
            result = await ensure_config()
            assert result is None


@pytest.mark.asyncio
async def test_ensure_config_post_message_exception(monkeypatch):
    """Test that ensure_config handles Exception when notifying relay of completion."""
    # Ensure no cloud keys in env
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    mock_session = MagicMock()
    mock_session.relay_url = "https://relay.example.com/setup#k=abc"
    mock_session.session_id = "test-session-id"

    with patch("mcp_relay_core.storage.config_file.read_config", return_value=None):
        with (
            patch(
                "mcp_relay_core.relay.client.create_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                return_value={"GEMINI_API_KEY": "fake-key"},
            ),
            patch("mcp_relay_core.storage.config_file.write_config"),
            patch("httpx.AsyncClient.post", side_effect=Exception("HTTP post failed")),
        ):
            result = await ensure_config()
            assert result is not None
            assert result["GEMINI_API_KEY"] == "fake-key"
            assert os.environ.get("GEMINI_API_KEY") == "fake-key"
