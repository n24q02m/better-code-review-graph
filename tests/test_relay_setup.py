"""Tests for relay_setup module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from better_code_review_graph.relay_schema import RELAY_SCHEMA
from better_code_review_graph.relay_setup import (
    CLOUD_KEYS,
    SERVER_NAME,
    apply_config,
    ensure_config,
)

# Test URL used when exercising the create_session path.
TEST_RELAY_URL = "https://relay.example.com"


@pytest.fixture(autouse=True)
def _default_relay_url_env(monkeypatch):
    """Set MCP_RELAY_URL for every test in this module.

    Per mode-matrix 2.5, remote-relay mode requires explicit MCP_RELAY_URL
    (no DEFAULT_RELAY_URL fallback). Tests that need to verify the "missing
    MCP_RELAY_URL" behavior can delenv it inside the test body.
    """
    monkeypatch.setenv("MCP_RELAY_URL", TEST_RELAY_URL)


class TestRelaySetupConstants:
    def test_server_name(self):
        assert SERVER_NAME == "better-code-review-graph"

    def test_cloud_keys(self):
        assert "JINA_AI_API_KEY" in CLOUD_KEYS
        assert "GEMINI_API_KEY" in CLOUD_KEYS
        assert "OPENAI_API_KEY" in CLOUD_KEYS
        assert "COHERE_API_KEY" in CLOUD_KEYS


class TestEnsureConfigEnvVar:
    async def test_returns_none_when_env_set(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaFakeKey123")
        result = await ensure_config()
        assert result is None

    async def test_any_cloud_key_takes_priority(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("JINA_AI_API_KEY", "jina_test")
        result = await ensure_config()
        assert result is None

    async def test_empty_env_var_not_accepted(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "")

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch(
                "mcp_core.relay.client.create_session",
                side_effect=Exception("no relay"),
            ):
                result = await ensure_config()
                assert result is None


class TestEnsureConfigFile:
    async def test_returns_config_from_file(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "from-file"
            }
            result = await ensure_config()
            assert result is not None
            assert result["GEMINI_API_KEY"] == "from-file"
            mock_store_cls.assert_called_once_with(SERVER_NAME)

    async def test_injects_config_into_env(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "injected-key"
            }
            await ensure_config()
            assert os.environ.get("GEMINI_API_KEY") == "injected-key"
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    async def test_returns_none_when_no_cloud_keys_in_file(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {"UNKNOWN_KEY": "value"}
            with patch(
                "mcp_core.relay.client.create_session",
                side_effect=Exception("no relay"),
            ):
                result = await ensure_config()
                assert result is None


class TestEnsureConfigRelay:
    async def test_missing_relay_url_raises(self, monkeypatch):
        """Remote-relay without MCP_RELAY_URL must raise per matrix 2.5."""
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("MCP_RELAY_URL", raising=False)
        with (
            patch(
                "better_code_review_graph.relay_setup.PerPluginStore"
            ) as mock_store_cls,
            pytest.raises(RuntimeError, match="MCP_RELAY_URL"),
        ):
            mock_store_cls.return_value.load.return_value = None
            await ensure_config()

    async def test_relay_success(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            mock_store_cls.return_value.save = MagicMock()
            mock_session = MagicMock()
            mock_session.relay_url = "https://relay.example.com/setup#k=abc"

            with (
                patch(
                    "mcp_core.relay.client.create_session",
                    new_callable=AsyncMock,
                    return_value=mock_session,
                ) as mock_create,
                patch(
                    "mcp_core.relay.client.poll_for_result",
                    new_callable=AsyncMock,
                    return_value={"JINA_AI_API_KEY": "from-relay"},
                ) as mock_poll,
                patch("httpx.AsyncClient") as _mock_http,
            ):
                result = await ensure_config()
                assert result is not None
                assert result["JINA_AI_API_KEY"] == "from-relay"
                mock_create.assert_called_once_with(
                    TEST_RELAY_URL, SERVER_NAME, RELAY_SCHEMA
                )
                mock_poll.assert_called_once()
                mock_store_cls.return_value.save.assert_called_once_with(
                    {"JINA_AI_API_KEY": "from-relay"}
                )

    async def test_relay_server_unreachable(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch(
                "mcp_core.relay.client.create_session",
                new_callable=AsyncMock,
                side_effect=ConnectionError("unreachable"),
            ):
                result = await ensure_config()
                assert result is None

    async def test_relay_timeout(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            mock_session = MagicMock()
            mock_session.relay_url = "https://relay.example.com/setup#k=abc"

            with (
                patch(
                    "mcp_core.relay.client.create_session",
                    new_callable=AsyncMock,
                    return_value=mock_session,
                ),
                patch(
                    "mcp_core.relay.client.poll_for_result",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("timed out"),
                ),
            ):
                result = await ensure_config()
                assert result is None

    async def test_relay_skipped(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            mock_session = MagicMock()
            mock_session.relay_url = "https://relay.example.com/setup#k=abc"

            with (
                patch(
                    "mcp_core.relay.client.create_session",
                    new_callable=AsyncMock,
                    return_value=mock_session,
                ),
                patch(
                    "mcp_core.relay.client.poll_for_result",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("RELAY_SKIPPED"),
                ),
            ):
                result = await ensure_config()
                assert result is None


class TestApplyConfig:
    def test_apply_config_sets_env(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)
        apply_config({"GEMINI_API_KEY": "applied"})
        assert os.environ.get("GEMINI_API_KEY") == "applied"
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def test_apply_config_skips_empty_and_existing(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("JINA_AI_API_KEY", "preexisting")
        apply_config({"JINA_AI_API_KEY": "new-value", "OPENAI_API_KEY": ""})
        # existing env var should NOT be overwritten
        assert os.environ.get("JINA_AI_API_KEY") == "preexisting"
        # empty value should NOT be applied
        assert os.environ.get("OPENAI_API_KEY") is None


class TestEnsureConfigFileReadException:
    async def test_read_config_exception_falls_through(self, monkeypatch):
        """PerPluginStore.load raising triggers the silent `except Exception: pass`."""
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.side_effect = OSError("corrupt file")
            with patch(
                "mcp_core.relay.client.create_session",
                side_effect=Exception("no relay"),
            ):
                result = await ensure_config()
                assert result is None


class TestEnsureConfigRelayNotifyFailure:
    async def test_relay_success_notify_complete_failure_non_fatal(self, monkeypatch):
        """httpx notify failure after poll success must not break the flow."""
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        mock_session = MagicMock()
        mock_session.relay_url = "https://relay.example.com/setup#k=abc"
        mock_session.session_id = "sess-notify-fail"

        class _FailingClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                raise ConnectionError("notify failed")

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            mock_store_cls.return_value.save = MagicMock()
            with (
                patch(
                    "mcp_core.relay.client.create_session",
                    new_callable=AsyncMock,
                    return_value=mock_session,
                ),
                patch(
                    "mcp_core.relay.client.poll_for_result",
                    new_callable=AsyncMock,
                    return_value={"GEMINI_API_KEY": "k"},
                ),
                patch("httpx.AsyncClient", _FailingClient),
            ):
                result = await ensure_config()
                assert result is not None
                assert result["GEMINI_API_KEY"] == "k"
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    async def test_relay_generic_runtime_error_other_message(self, monkeypatch):
        """RuntimeError with neither RELAY_SKIPPED nor 'timed out' -> else branch."""
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        mock_session = MagicMock()
        mock_session.relay_url = "https://relay.example.com/setup#k=abc"

        with patch(
            "better_code_review_graph.relay_setup.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with (
                patch(
                    "mcp_core.relay.client.create_session",
                    new_callable=AsyncMock,
                    return_value=mock_session,
                ),
                patch(
                    "mcp_core.relay.client.poll_for_result",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("some other issue"),
                ),
            ):
                result = await ensure_config()
                assert result is None


# ---------------------------------------------------------------------------
# Extra coverage from test_relay_setup_coverage_fix.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_config_exception_constructor(monkeypatch):
    """Cover the case where PerPluginStore constructor itself raises."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    # PerPluginStore constructor raises Exception -- should fall through to relay
    with patch(
        "better_code_review_graph.relay_setup.PerPluginStore",
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
async def test_httpx_post_exception_direct(monkeypatch):
    """Direct port of test_httpx_post_exception from coverage fix file."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    mock_session = MagicMock()
    mock_session.relay_url = "https://relay.example.com/setup"
    mock_session.session_id = "test-session"

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=Exception("Network error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("better_code_review_graph.relay_setup.PerPluginStore") as mock_store_cls:
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
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_poll_for_result_runtime_error_unexpected_direct(monkeypatch):
    """Direct port of test_poll_for_result_runtime_error_unexpected."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)

    with patch("better_code_review_graph.relay_setup.PerPluginStore") as mock_store_cls:
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
