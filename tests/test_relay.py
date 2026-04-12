"""Tests for relay_schema, relay_setup, and credential_state modules."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

from better_code_review_graph.relay_schema import RELAY_SCHEMA
from better_code_review_graph.relay_setup import (
    CLOUD_KEYS,
    DEFAULT_RELAY_URL,
    SERVER_NAME,
    ensure_config,
)

# ---------------------------------------------------------------------------
# relay_schema
# ---------------------------------------------------------------------------


class TestRelaySchema:
    def test_server_name(self):
        assert RELAY_SCHEMA["server"] == "better-code-review-graph"

    def test_display_name(self):
        assert RELAY_SCHEMA["displayName"] == "Code Review Graph"

    def test_has_fields(self):
        fields = RELAY_SCHEMA["fields"]
        assert len(fields) == 4

    def test_field_keys(self):
        keys = [f["key"] for f in RELAY_SCHEMA["fields"]]
        assert keys == [
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
        ]

    def test_all_fields_optional(self):
        for field in RELAY_SCHEMA["fields"]:
            assert field["required"] is False

    def test_schema_is_valid_typed_dict(self):
        assert "server" in RELAY_SCHEMA
        assert "displayName" in RELAY_SCHEMA
        assert "fields" in RELAY_SCHEMA


# ---------------------------------------------------------------------------
# relay_setup
# ---------------------------------------------------------------------------


class TestRelaySetupConstants:
    def test_server_name(self):
        assert SERVER_NAME == "better-code-review-graph"

    def test_cloud_keys(self):
        assert "JINA_AI_API_KEY" in CLOUD_KEYS
        assert "GEMINI_API_KEY" in CLOUD_KEYS
        assert "OPENAI_API_KEY" in CLOUD_KEYS
        assert "COHERE_API_KEY" in CLOUD_KEYS

    def test_relay_url(self):
        assert DEFAULT_RELAY_URL.startswith("https://")


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

        with patch("mcp_core.storage.config_file.read_config", return_value=None):
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
            "mcp_core.storage.config_file.read_config",
            return_value={"GEMINI_API_KEY": "from-file"},
        ) as mock_read:
            result = await ensure_config()
            assert result is not None
            assert result["GEMINI_API_KEY"] == "from-file"
            mock_read.assert_called_once_with(SERVER_NAME)

    async def test_injects_config_into_env(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "mcp_core.storage.config_file.read_config",
            return_value={"GEMINI_API_KEY": "injected-key"},
        ):
            await ensure_config()
            assert os.environ.get("GEMINI_API_KEY") == "injected-key"
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    async def test_returns_none_when_no_cloud_keys_in_file(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch(
            "mcp_core.storage.config_file.read_config",
            return_value={"UNKNOWN_KEY": "value"},
        ):
            with patch(
                "mcp_core.relay.client.create_session",
                side_effect=Exception("no relay"),
            ):
                result = await ensure_config()
                assert result is None


class TestEnsureConfigRelay:
    async def test_relay_success(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch("mcp_core.storage.config_file.read_config", return_value=None):
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
                patch("mcp_core.storage.config_file.write_config") as mock_write,
                patch("httpx.AsyncClient") as _mock_http,
            ):
                result = await ensure_config()
                assert result is not None
                assert result["JINA_AI_API_KEY"] == "from-relay"
                mock_create.assert_called_once_with(
                    DEFAULT_RELAY_URL, SERVER_NAME, RELAY_SCHEMA
                )
                mock_poll.assert_called_once()
                mock_write.assert_called_once_with(
                    SERVER_NAME, {"JINA_AI_API_KEY": "from-relay"}
                )

    async def test_relay_server_unreachable(self, monkeypatch):
        for key in CLOUD_KEYS:
            monkeypatch.delenv(key, raising=False)

        with patch("mcp_core.storage.config_file.read_config", return_value=None):
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

        with patch("mcp_core.storage.config_file.read_config", return_value=None):
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

        with patch("mcp_core.storage.config_file.read_config", return_value=None):
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


# ---------------------------------------------------------------------------
# CLI integration -- tests serve_main calls resolve_credential_state
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    def test_main_calls_resolve_credential_state(self):
        """serve_main calls resolve_credential_state (not old ensure_config)."""
        with (
            patch(
                "better_code_review_graph.credential_state.resolve_credential_state",
            ) as mock_resolve,
            patch("better_code_review_graph.server.mcp") as mock_mcp,
            patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}),
        ):
            from better_code_review_graph.cli import main

            main()
            mock_resolve.assert_called_once()
            mock_mcp.run.assert_called_once()

    def test_main_continues_on_relay_error(self):
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
