import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from better_code_review_graph.relay_setup import (
    CLOUD_KEYS,
    ensure_config,
)


@pytest.fixture(autouse=True)
def _default_relay_url_env(monkeypatch):
    """Set MCP_RELAY_URL for every test in this module per mode-matrix 2.5."""
    monkeypatch.setenv("MCP_RELAY_URL", "https://relay.example.com")


@pytest.mark.asyncio
async def test_read_config_exception(monkeypatch):
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    # Line 64-65: read_config raises Exception
    with patch(
        "mcp_core.storage.config_file.read_config",
        side_effect=Exception("Disk error"),
    ):
        # To avoid going into relay setup, we also mock create_session to fail
        with patch(
            "mcp_core.relay.client.create_session",
            side_effect=Exception("no relay"),
        ):
            result = await ensure_config()
            assert result is None


@pytest.mark.asyncio
async def test_httpx_post_exception(monkeypatch):
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("mcp_core.storage.config_file.read_config", return_value=None):
        mock_session = MagicMock()
        mock_session.relay_url = "https://relay.example.com/setup"
        mock_session.session_id = "test-session"

        # Mock create_session and poll_for_result to succeed
        with patch(
            "mcp_core.relay.client.create_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            with patch(
                "mcp_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                return_value={"GEMINI_API_KEY": "new-key"},
            ):
                with patch("mcp_core.storage.config_file.write_config"):
                    # Line 111-112: httpx post raises Exception
                    with patch("httpx.AsyncClient") as mock_client_class:
                        mock_client = MagicMock()
                        mock_client.post = AsyncMock(
                            side_effect=Exception("Network error")
                        )
                        mock_client.__aenter__.return_value = mock_client
                        mock_client_class.return_value = mock_client

                        result = await ensure_config()
                        assert result is not None
                        assert result["GEMINI_API_KEY"] == "new-key"
                        assert os.environ.get("GEMINI_API_KEY") == "new-key"


@pytest.mark.asyncio
async def test_poll_for_result_runtime_error_unexpected(monkeypatch):
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("mcp_core.storage.config_file.read_config", return_value=None):
        mock_session = MagicMock()
        mock_session.relay_url = "https://relay.example.com/setup"

        with patch(
            "mcp_core.relay.client.create_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            # Line 126: RuntimeError with unexpected message
            with patch(
                "mcp_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("something went wrong"),
            ):
                result = await ensure_config()
                assert result is None
