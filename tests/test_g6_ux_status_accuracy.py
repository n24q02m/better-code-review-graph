"""G6 UX bug fixes — setup_status accuracy for better-code-review-graph.

Bug: setup_status returned stale module-level _state even when no
credentials were actually loadable via PerPluginStore.

Fix: setup_status now derives state from live PerPluginStore load + env,
and always includes providers_configured in the response.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest


def _call_config_setup_status_sync() -> dict[str, Any]:
    """Invoke the async server config action and return parsed dict."""
    import asyncio

    from better_code_review_graph.server import config

    raw = asyncio.run(config(action="setup_status"))
    return json.loads(raw)


class TestSetupStatusLiveDerivedState:
    """setup_status derives state from live PerPluginStore, not stale _state."""

    def test_returns_configured_when_store_has_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_status returns configured when PerPluginStore has cloud keys."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("JINA_AI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("CO_API_KEY", raising=False)

        with patch(
            "mcp_core.storage.per_plugin_store.PerPluginStore.load",
            return_value={"GEMINI_API_KEY": "test-key-123"},
        ):
            result = _call_config_setup_status_sync()

        assert result["state"] == "configured"
        assert "GEMINI_API_KEY" in result["providers_configured"]

    def test_returns_needs_setup_when_store_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_status returns awaiting_setup when store empty and no env vars."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("JINA_AI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("CO_API_KEY", raising=False)

        # Force module-level state to CONFIGURED (stale) to reproduce the bug
        import better_code_review_graph.credential_state as cs

        cs.set_state(cs.CredentialState.CONFIGURED)

        with patch(
            "mcp_core.storage.per_plugin_store.PerPluginStore.load",
            return_value={},
        ):
            result = _call_config_setup_status_sync()

        # State must be derived from live creds, NOT stale _state
        assert result["state"] != "configured"
        assert result["providers_configured"] == []

        # Restore state
        cs.set_state(cs.CredentialState.AWAITING_SETUP)

    def test_env_vars_take_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_status includes env-var keys in providers_configured."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("JINA_AI_API_KEY", raising=False)
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("CO_API_KEY", raising=False)

        with patch(
            "mcp_core.storage.per_plugin_store.PerPluginStore.load",
            return_value={},
        ):
            result = _call_config_setup_status_sync()

        assert result["state"] == "configured"
        assert "OPENAI_API_KEY" in result["providers_configured"]
        assert "OPENAI_API_KEY" in result["cloud_keys_in_env"]

    def test_response_includes_providers_configured_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_status always includes providers_configured key in response."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("JINA_AI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("CO_API_KEY", raising=False)

        with patch(
            "mcp_core.storage.per_plugin_store.PerPluginStore.load",
            return_value={},
        ):
            result = _call_config_setup_status_sync()

        assert "providers_configured" in result
        assert isinstance(result["providers_configured"], list)

    def test_no_duplicate_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If same key appears in both env and store, it should appear only once."""
        monkeypatch.setenv("GEMINI_API_KEY", "key-from-env")

        with patch(
            "mcp_core.storage.per_plugin_store.PerPluginStore.load",
            return_value={"GEMINI_API_KEY": "key-from-store"},
        ):
            result = _call_config_setup_status_sync()

        assert result["providers_configured"].count("GEMINI_API_KEY") == 1
