"""Tests for relay_schema and relay_setup modules."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

from better_code_review_graph.relay_schema import RELAY_SCHEMA
from better_code_review_graph.relay_setup import (
    DEFAULT_RELAY_URL,
    REQUIRED_FIELDS,
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
        assert len(fields) == 1

    def test_gemini_api_key_field(self):
        field = RELAY_SCHEMA["fields"][0]
        assert field["key"] == "GEMINI_API_KEY"
        assert field["type"] == "password"
        assert "AIza" in field["placeholder"]
        assert "aistudio.google.com" in field["helpUrl"]

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

    def test_required_fields(self):
        assert REQUIRED_FIELDS == ["GEMINI_API_KEY"]

    def test_relay_url(self):
        assert DEFAULT_RELAY_URL.startswith("https://")


class TestEnsureConfigEnvVar:
    async def test_returns_config_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaFakeKey123")
        result = await ensure_config()
        assert result is not None
        assert result["GEMINI_API_KEY"] == "AIzaFakeKey123"

    async def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "from-env")
        with patch("mcp_relay_core.storage.resolver.resolve_config") as mock_resolve:
            result = await ensure_config()
            # resolve_config should NOT be called when env var is present
            mock_resolve.assert_not_called()
            assert result["GEMINI_API_KEY"] == "from-env"

    async def test_empty_env_var_not_accepted(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "")
        with patch("mcp_relay_core.storage.resolver.resolve_config") as mock_resolve:
            mock_result = MagicMock()
            mock_result.config = None
            mock_result.source = None
            mock_resolve.return_value = mock_result

            with patch(
                "mcp_relay_core.relay.client.create_session",
                side_effect=Exception("no relay"),
            ):
                result = await ensure_config()
                assert result is None


class TestEnsureConfigFile:
    async def test_returns_config_from_file(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with patch("mcp_relay_core.storage.resolver.resolve_config") as mock_resolve:
            mock_result = MagicMock()
            mock_result.config = {"GEMINI_API_KEY": "from-file"}
            mock_result.source = "file"
            mock_resolve.return_value = mock_result

            result = await ensure_config()
            assert result is not None
            assert result["GEMINI_API_KEY"] == "from-file"
            mock_resolve.assert_called_once_with(SERVER_NAME, REQUIRED_FIELDS)

    async def test_injects_config_into_env(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with patch("mcp_relay_core.storage.resolver.resolve_config") as mock_resolve:
            mock_result = MagicMock()
            mock_result.config = {"GEMINI_API_KEY": "injected-key"}
            mock_result.source = "file"
            mock_resolve.return_value = mock_result

            await ensure_config()
            assert os.environ.get("GEMINI_API_KEY") == "injected-key"
            # Clean up
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)


class TestEnsureConfigRelay:
    async def test_relay_success(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with patch("mcp_relay_core.storage.resolver.resolve_config") as mock_resolve:
            mock_result = MagicMock()
            mock_result.config = None
            mock_result.source = None
            mock_resolve.return_value = mock_result

            mock_session = MagicMock()
            mock_session.relay_url = "https://relay.example.com/setup#k=abc"

            with (
                patch(
                    "mcp_relay_core.relay.client.create_session",
                    new_callable=AsyncMock,
                    return_value=mock_session,
                ) as mock_create,
                patch(
                    "mcp_relay_core.relay.client.poll_for_result",
                    new_callable=AsyncMock,
                    return_value={"GEMINI_API_KEY": "from-relay"},
                ) as mock_poll,
                patch("mcp_relay_core.storage.config_file.write_config") as mock_write,
            ):
                result = await ensure_config()
                assert result is not None
                assert result["GEMINI_API_KEY"] == "from-relay"
                mock_create.assert_called_once_with(
                    DEFAULT_RELAY_URL, SERVER_NAME, RELAY_SCHEMA
                )
                mock_poll.assert_called_once_with(DEFAULT_RELAY_URL, mock_session)
                mock_write.assert_called_once_with(
                    SERVER_NAME, {"GEMINI_API_KEY": "from-relay"}
                )

    async def test_relay_server_unreachable(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with patch("mcp_relay_core.storage.resolver.resolve_config") as mock_resolve:
            mock_result = MagicMock()
            mock_result.config = None
            mock_result.source = None
            mock_resolve.return_value = mock_result

            with patch(
                "mcp_relay_core.relay.client.create_session",
                new_callable=AsyncMock,
                side_effect=ConnectionError("unreachable"),
            ):
                result = await ensure_config()
                assert result is None

    async def test_relay_timeout(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with patch("mcp_relay_core.storage.resolver.resolve_config") as mock_resolve:
            mock_result = MagicMock()
            mock_result.config = None
            mock_result.source = None
            mock_resolve.return_value = mock_result

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
                    side_effect=RuntimeError("timeout"),
                ),
            ):
                result = await ensure_config()
                assert result is None


class TestCLIIntegration:
    def test_main_calls_ensure_config(self):
        with (
            patch(
                "better_code_review_graph.relay_setup.ensure_config",
                new_callable=AsyncMock,
                return_value={"GEMINI_API_KEY": "test"},
            ) as mock_ensure,
            patch("better_code_review_graph.server.mcp") as mock_mcp,
        ):
            from better_code_review_graph.cli import main

            main()
            mock_ensure.assert_called_once()
            mock_mcp.run.assert_called_once()

    def test_main_continues_on_relay_error(self):
        with (
            patch(
                "better_code_review_graph.relay_setup.ensure_config",
                new_callable=AsyncMock,
                side_effect=Exception("relay broken"),
            ),
            patch("better_code_review_graph.server.mcp") as mock_mcp,
        ):
            from better_code_review_graph.cli import main

            main()
            # Server should still start even if relay fails
            mock_mcp.run.assert_called_once()
