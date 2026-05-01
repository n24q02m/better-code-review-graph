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

    # PerPluginStore constructor raises Exception -- should fall through to relay
    with patch(
        "better_code_review_graph.credential_state.PerPluginStore",
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

    mock_session = MagicMock()
    mock_session.relay_url = "https://relay.example.com/setup"
    mock_session.session_id = "test-session"

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=Exception("Network error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("better_code_review_graph.credential_state.PerPluginStore") as mock_store_cls:
        mock_store_cls.return_value.load.return_value = None
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
                with patch("httpx.AsyncClient", return_value=mock_client):
                    result = await ensure_config()
                    assert result is not None
                    assert result["GEMINI_API_KEY"] == "new-key"
                    assert os.environ.get("GEMINI_API_KEY") == "new-key"


@pytest.mark.asyncio
async def test_poll_for_result_runtime_error_unexpected(monkeypatch):
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("better_code_review_graph.credential_state.PerPluginStore") as mock_store_cls:
        mock_store_cls.return_value.load.return_value = None
        mock_session = MagicMock()
        mock_session.relay_url = "https://relay.example.com/setup"

        with patch(
            "mcp_core.relay.client.create_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            # RuntimeError with unexpected message -- should return None
            with patch(
                "mcp_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("something went wrong"),
            ):
                result = await ensure_config()
                assert result is None
