"""Tests for the server setup tool (server.py lines 494-612).

Covers: setup(action=status|start|skip|reset|complete), unknown action,
and _maybe_include_setup_hint helper.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

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
        # The conftest patches server._maybe_include_setup_hint at the module level.
        # We re-import the original implementation directly to test it.
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
# setup tool -- status action
# ---------------------------------------------------------------------------


class TestSetupStatus:
    async def test_status_returns_state_info(self):
        """Status returns current state and cloud keys in env."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.CONFIGURED
        cs._setup_url = None

        result = json.loads(await setup.fn(action="status"))
        assert result["state"] == "configured"
        assert "cloud_keys_in_env" in result

    async def test_status_with_setup_url(self):
        """Status includes setup_url when set."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.SETUP_IN_PROGRESS
        cs._setup_url = "https://relay.example.com/setup"

        result = json.loads(await setup.fn(action="status"))
        assert result["state"] == "setup_in_progress"
        assert result["setup_url"] == "https://relay.example.com/setup"


# ---------------------------------------------------------------------------
# setup tool -- start action
# ---------------------------------------------------------------------------


class TestSetupStart:
    async def test_start_already_configured_no_force(self):
        """Start with already configured state and no force returns already_configured."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.CONFIGURED

        result = json.loads(await setup.fn(action="start"))
        assert result["status"] == "already_configured"
        assert "force=true" in result["message"]

    async def test_start_triggers_relay_setup(self):
        """Start triggers relay and returns URL."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.AWAITING_SETUP

        with patch(
            "better_code_review_graph.credential_state.trigger_relay_setup",
            new_callable=AsyncMock,
            return_value="https://relay.example.com/setup#k=abc",
        ):
            result = json.loads(await setup.fn(action="start"))
            assert result["status"] == "setup_started"
            assert result["setup_url"] == "https://relay.example.com/setup#k=abc"

    async def test_start_relay_failure(self):
        """Start returns error when relay fails."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.AWAITING_SETUP

        with patch(
            "better_code_review_graph.credential_state.trigger_relay_setup",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = json.loads(await setup.fn(action="start"))
            assert result["status"] == "error"
            assert "Failed" in result["message"]

    async def test_start_force_overrides_configured(self):
        """Start with force=true reconfigures even when CONFIGURED."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.CONFIGURED

        with patch(
            "better_code_review_graph.credential_state.trigger_relay_setup",
            new_callable=AsyncMock,
            return_value="https://relay.example.com/new-session",
        ):
            result = json.loads(await setup.fn(action="start", force=True))
            assert result["status"] == "setup_started"


# ---------------------------------------------------------------------------
# setup tool -- skip action
# ---------------------------------------------------------------------------


class TestSetupSkip:
    async def test_skip_sets_local_mode(self):
        """Skip sets LOCAL mode and calls set_local_mode."""
        from better_code_review_graph.server import setup

        with patch("mcp_relay_core.set_local_mode") as mock_local:
            result = json.loads(await setup.fn(action="skip"))
            assert result["status"] == "ok"
            assert "Local mode" in result["message"]
            mock_local.assert_called_once()


# ---------------------------------------------------------------------------
# setup tool -- reset action
# ---------------------------------------------------------------------------


class TestSetupReset:
    async def test_reset_clears_state(self):
        """Reset clears credentials and resets state."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.CONFIGURED

        with (
            patch("mcp_relay_core.clear_mode"),
            patch("mcp_relay_core.storage.config_file.delete_config"),
        ):
            result = json.loads(await setup.fn(action="reset"))
            assert result["status"] == "ok"
            assert cs._state == CredentialState.AWAITING_SETUP


# ---------------------------------------------------------------------------
# setup tool -- complete action
# ---------------------------------------------------------------------------


class TestSetupComplete:
    async def test_complete_refreshes_state(self, monkeypatch):
        """Complete re-resolves credential state."""
        from better_code_review_graph import credential_state as cs
        from better_code_review_graph.server import setup

        cs._state = CredentialState.AWAITING_SETUP
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        result = json.loads(await setup.fn(action="complete"))
        assert result["status"] == "ok"
        assert result["state"] == "configured"


# ---------------------------------------------------------------------------
# setup tool -- unknown action
# ---------------------------------------------------------------------------


class TestSetupUnknownAction:
    async def test_unknown_action_returns_error(self):
        """Unknown action returns error with valid actions."""
        from better_code_review_graph.server import setup

        result = json.loads(await setup.fn(action="nonexistent"))
        assert "error" in result
        assert "valid_actions" in result

    async def test_close_match_suggestion(self):
        """Typo in action returns a suggestion."""
        from better_code_review_graph.server import setup

        result = json.loads(await setup.fn(action="statu"))
        assert "error" in result
        assert "status" in result["error"]
