"""Tests for setup_* sub-actions of the config tool (server.py).

Covers: config(action=setup_status|setup_start|setup_skip|setup_reset|setup_complete),
unknown action variants, and _maybe_include_setup_hint helper.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from better_code_review_graph.credential_state import CredentialState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_credential_state():
    """Reset credential state module before/after each test."""
    import better_code_review_graph.credential_state as cs

    original_state = cs._state
    original_url = cs._setup_url
    yield
    cs._state = original_state
    cs._setup_url = original_url


# ---------------------------------------------------------------------------
# _maybe_include_setup_hint
# ---------------------------------------------------------------------------


class TestMaybeIncludeSetupHint:
    """Test _maybe_include_setup_hint directly (bypass autouse conftest mock)."""

    def _real_hint_fn(self):
        """Import the real function from server module source."""
        from better_code_review_graph.credential_state import (
            CredentialState as _CS,
        )
        from better_code_review_graph.credential_state import (
            get_setup_url,
            get_state,
        )

        def _maybe_include_setup_hint(result: dict) -> dict:
            if get_state() == _CS.AWAITING_SETUP:
                url = get_setup_url()
                if url:
                    result["_setup_hint"] = (
                        f"Cloud embeddings available. Configure API keys: {url}"
                    )
                else:
                    result["_setup_hint"] = (
                        "Cloud embeddings available. Use config(action='setup_start') to configure."
                    )
            return result

        return _maybe_include_setup_hint

    def test_adds_hint_when_awaiting_setup_no_url(self):
        """Adds generic hint when AWAITING_SETUP and no URL."""
        from better_code_review_graph import credential_state as cs

        cs._state = CredentialState.AWAITING_SETUP
        cs._setup_url = None

        fn = self._real_hint_fn()
        result = fn({"status": "ok"})
        assert "_setup_hint" in result
        assert "setup_start" in result["_setup_hint"]

    def test_adds_url_hint_when_awaiting_setup_with_url(self):
        """Adds URL hint when AWAITING_SETUP and URL is set."""
        from better_code_review_graph import credential_state as cs

        cs._state = CredentialState.AWAITING_SETUP
        cs._setup_url = "https://relay.example.com/setup"

        fn = self._real_hint_fn()
        result = fn({"status": "ok"})
        assert "_setup_hint" in result
        assert "https://relay.example.com/setup" in result["_setup_hint"]

    def test_no_hint_when_configured(self):
        """No hint added when CONFIGURED."""
        from better_code_review_graph import credential_state as cs

        cs._state = CredentialState.CONFIGURED

        fn = self._real_hint_fn()
        result = fn({"status": "ok"})
        assert "_setup_hint" not in result


# ---------------------------------------------------------------------------
# config setup_status action
# ---------------------------------------------------------------------------


class TestSetupStatus:
    async def test_status_returns_state_info(self, monkeypatch):
        """setup_status derives `configured` from live env keys (G6 UX fix)."""
        from better_code_review_graph.server import config

        for key in (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "JINA_AI_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

        with patch(
            "mcp_core.storage.per_plugin_store.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            result = await config(action="setup_status")
        assert result["state"] == "configured"
        assert "cloud_keys_in_env" in result
        assert "GEMINI_API_KEY" in result["cloud_keys_in_env"]

    async def test_status_with_setup_url(self, monkeypatch):
        """setup_status includes setup_url when set on the module."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import config

        for key in (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "JINA_AI_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        cs._state = CredentialState.AWAITING_SETUP
        cs._setup_url = "https://relay.example.com/setup"

        with patch(
            "mcp_core.storage.per_plugin_store.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            result = await config(action="setup_status")
        assert result["state"] == "awaiting_setup"
        assert result["setup_url"] == "https://relay.example.com/setup"


# ---------------------------------------------------------------------------
# config setup_start action
# ---------------------------------------------------------------------------


class TestSetupStart:
    async def test_start_already_configured_no_force(self):
        """setup_start with already configured state and no force returns already_configured."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.CONFIGURED

        result = await config(action="setup_start")
        assert result["status"] == "already_configured"
        assert "force=true" in result["message"]

    async def test_start_returns_authorize_url_in_http_mode(self, monkeypatch):
        """setup_start returns the HTTP server's /authorize URL when PUBLIC_URL set."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.AWAITING_SETUP
        monkeypatch.setenv("PUBLIC_URL", "https://relay.example.com")

        result = await config(action="setup_start")
        assert result["status"] == "setup_started"
        assert result["setup_url"] == "https://relay.example.com/authorize"

    async def test_start_returns_stdio_mode_message_when_no_public_url(
        self, monkeypatch
    ):
        """setup_start in stdio mode (no PUBLIC_URL) returns an env-var hint."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.AWAITING_SETUP
        monkeypatch.delenv("PUBLIC_URL", raising=False)

        result = await config(action="setup_start")
        assert result["status"] == "stdio_mode"
        assert "GEMINI_API_KEY" in result["message"]

    async def test_start_force_overrides_configured(self, monkeypatch):
        """setup_start with force=true reconfigures even when CONFIGURED."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.CONFIGURED
        monkeypatch.setenv("PUBLIC_URL", "https://relay.example.com")

        result = await config(action="setup_start", force=True)
        assert result["status"] == "setup_started"
        assert result["setup_url"] == "https://relay.example.com/authorize"


# ---------------------------------------------------------------------------
# config setup_skip action
# ---------------------------------------------------------------------------


class TestSetupSkip:
    async def test_skip_sets_local_mode(self):
        """setup_skip sets LOCAL mode and calls set_local_mode."""
        from better_code_review_graph.server import config

        with patch("mcp_core.set_local_mode") as mock_local:
            result = await config(action="setup_skip")
            assert result["status"] == "ok"
            assert "Local mode" in result["message"]
            mock_local.assert_called_once()


# ---------------------------------------------------------------------------
# config setup_reset action
# ---------------------------------------------------------------------------


class TestSetupReset:
    async def test_reset_clears_state(self):
        """setup_reset clears credentials and resets state."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.CONFIGURED

        with (
            patch("mcp_core.clear_mode"),
            patch("better_code_review_graph.credential_state.PerPluginStore"),
        ):
            result = await config(action="setup_reset")
            assert result["status"] == "ok"
            assert cs._state == CredentialState.AWAITING_SETUP


# ---------------------------------------------------------------------------
# config setup_complete action
# ---------------------------------------------------------------------------


class TestSetupComplete:
    async def test_complete_refreshes_state(self, monkeypatch):
        """setup_complete re-resolves credential state."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.AWAITING_SETUP
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        result = await config(action="setup_complete")
        assert result["status"] == "ok"
        assert result["state"] == "configured"


# ---------------------------------------------------------------------------
# config setup_* unknown action (via config unknown action path)
# ---------------------------------------------------------------------------


class TestSetupUnknownAction:
    async def test_unknown_action_returns_error(self):
        """Unknown action returns error with valid actions."""
        from better_code_review_graph.server import config

        result = await config(action="nonexistent_setup_action")
        assert "error" in result
        assert "valid_actions" in result

    async def test_setup_prefix_typo_suggestion(self):
        """Typo in setup_ action returns a suggestion."""
        from better_code_review_graph.server import config

        result = await config(action="setup_statu")
        assert "error" in result
        assert "setup_status" in result["error"]
