"""Tests for credential_state module -- non-blocking credential state machine.

Covers: CredentialState enum, resolve_credential_state(), trigger_relay_setup(),
_poll_relay_background(), _share_cloud_keys_to_peers(), set_state(), reset_state(),
get_state(), get_setup_url().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from better_code_review_graph.credential_state import (
    CLOUD_KEYS,
    DEFAULT_RELAY_URL,
    SERVER_NAME,
    CredentialState,
    _share_cloud_keys_to_peers,
    get_setup_url,
    get_state,
    reset_state,
    resolve_credential_state,
    set_state,
    trigger_relay_setup,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state before and after each test."""
    import better_code_review_graph.credential_state as cs

    cs._state = CredentialState.AWAITING_SETUP
    cs._setup_url = None
    yield
    cs._state = CredentialState.AWAITING_SETUP
    cs._setup_url = None


@pytest.fixture
def _clean_env(monkeypatch):
    """Remove all cloud keys from environment."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_server_name(self):
        assert SERVER_NAME == "better-code-review-graph"

    def test_default_relay_url(self):
        assert DEFAULT_RELAY_URL.startswith("https://")

    def test_cloud_keys_contains_expected(self):
        assert "GEMINI_API_KEY" in CLOUD_KEYS
        assert "GOOGLE_API_KEY" in CLOUD_KEYS
        assert "JINA_AI_API_KEY" in CLOUD_KEYS
        assert "OPENAI_API_KEY" in CLOUD_KEYS
        assert "COHERE_API_KEY" in CLOUD_KEYS
        assert "CO_API_KEY" in CLOUD_KEYS

    def test_credential_state_enum_values(self):
        assert CredentialState.AWAITING_SETUP.value == "awaiting_setup"
        assert CredentialState.SETUP_IN_PROGRESS.value == "setup_in_progress"
        assert CredentialState.CONFIGURED.value == "configured"
        assert CredentialState.LOCAL.value == "local"


# ---------------------------------------------------------------------------
# get_state / get_setup_url / set_state / reset_state
# ---------------------------------------------------------------------------


class TestStateAccessors:
    def test_initial_state_is_awaiting(self):
        assert get_state() == CredentialState.AWAITING_SETUP

    def test_initial_setup_url_is_none(self):
        assert get_setup_url() is None

    def test_set_state_changes_state(self):
        set_state(CredentialState.CONFIGURED)
        assert get_state() == CredentialState.CONFIGURED

    def test_set_state_to_local(self):
        set_state(CredentialState.LOCAL)
        assert get_state() == CredentialState.LOCAL

    def test_set_state_to_setup_in_progress(self):
        set_state(CredentialState.SETUP_IN_PROGRESS)
        assert get_state() == CredentialState.SETUP_IN_PROGRESS

    def test_reset_state_clears_everything(self):
        import better_code_review_graph.credential_state as cs

        cs._state = CredentialState.CONFIGURED
        cs._setup_url = "https://example.com/setup"

        with (
            patch("mcp_relay_core.clear_mode") as mock_clear,
            patch("mcp_relay_core.storage.config_file.delete_config") as mock_delete,
        ):
            reset_state()
            assert get_state() == CredentialState.AWAITING_SETUP
            assert get_setup_url() is None
            mock_clear.assert_called_once_with(SERVER_NAME)
            mock_delete.assert_called_once_with(SERVER_NAME)

    def test_reset_state_handles_import_error(self):
        """reset_state silently handles exceptions from relay core."""
        import better_code_review_graph.credential_state as cs

        cs._state = CredentialState.CONFIGURED
        cs._setup_url = "https://example.com/setup"

        with patch(
            "mcp_relay_core.clear_mode",
            side_effect=ImportError("no relay core"),
        ):
            reset_state()
            assert get_state() == CredentialState.AWAITING_SETUP
            assert get_setup_url() is None


# ---------------------------------------------------------------------------
# resolve_credential_state
# ---------------------------------------------------------------------------


class TestResolveCredentialState:
    def test_env_var_sets_configured(self, monkeypatch, _clean_env):
        """Step 1: any cloud key in env -> CONFIGURED."""
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaTestKey123")
        result = resolve_credential_state()
        assert result == CredentialState.CONFIGURED
        assert get_state() == CredentialState.CONFIGURED

    def test_any_cloud_key_works(self, monkeypatch, _clean_env):
        """Each cloud key individually triggers CONFIGURED."""
        for key in CLOUD_KEYS:
            set_state(CredentialState.AWAITING_SETUP)
            for k in CLOUD_KEYS:
                monkeypatch.delenv(k, raising=False)
            monkeypatch.setenv(key, "test-value")
            result = resolve_credential_state()
            assert result == CredentialState.CONFIGURED, f"Failed for {key}"

    def test_empty_env_var_not_accepted(self, monkeypatch, _clean_env):
        """Empty string env vars are falsy, don't count as configured."""
        monkeypatch.setenv("GEMINI_API_KEY", "")
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            return_value=None,
        ):
            with patch("mcp_relay_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_config_file_sets_configured(self, monkeypatch, _clean_env):
        """Step 2: saved config with cloud keys -> CONFIGURED + env injected."""
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            return_value={"GEMINI_API_KEY": "from-config", "JINA_AI_API_KEY": "jina-cfg"},
        ):
            with patch(
                "better_code_review_graph.credential_state._share_cloud_keys_to_peers"
            ) as mock_share:
                result = resolve_credential_state()
                assert result == CredentialState.CONFIGURED
                assert monkeypatch.setenv  # env vars should have been set
                mock_share.assert_called_once()

    def test_config_file_injects_env(self, monkeypatch, _clean_env):
        """Config values are injected into environment."""
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            return_value={"GEMINI_API_KEY": "injected-from-config"},
        ):
            with patch(
                "better_code_review_graph.credential_state._share_cloud_keys_to_peers"
            ):
                resolve_credential_state()
                assert (
                    monkeypatch.setenv is not None
                )  # monkeypatch is active so env changes are safe

    def test_config_file_no_cloud_keys(self, monkeypatch, _clean_env):
        """Config file with no cloud keys -> falls through."""
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            return_value={"UNKNOWN_KEY": "value"},
        ):
            with patch("mcp_relay_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_config_file_read_exception(self, monkeypatch, _clean_env):
        """Config file read failure -> falls through silently."""
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            side_effect=ImportError("no relay core"),
        ):
            with patch("mcp_relay_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_local_mode_marker(self, monkeypatch, _clean_env):
        """Step 3: local mode marker -> LOCAL."""
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            return_value=None,
        ):
            with patch("mcp_relay_core.get_mode", return_value="local"):
                result = resolve_credential_state()
                assert result == CredentialState.LOCAL

    def test_local_mode_marker_exception(self, monkeypatch, _clean_env):
        """get_mode exception -> falls through to AWAITING_SETUP."""
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            return_value=None,
        ):
            with patch(
                "mcp_relay_core.get_mode",
                side_effect=ImportError("no relay"),
            ):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_nothing_found_awaiting_setup(self, monkeypatch, _clean_env):
        """Step 4: nothing found -> AWAITING_SETUP."""
        with patch(
            "mcp_relay_core.storage.config_file.read_config",
            return_value=None,
        ):
            with patch("mcp_relay_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP


# ---------------------------------------------------------------------------
# _share_cloud_keys_to_peers
# ---------------------------------------------------------------------------


class TestShareCloudKeysToPeers:
    def test_shares_to_wet_and_mnemo(self):
        """Writes shared cloud keys to wet-mcp and mnemo-mcp."""
        config = {"GEMINI_API_KEY": "test-key", "JINA_AI_API_KEY": "jina-key"}
        with patch("mcp_relay_core.storage.config_file.write_config") as mock_write:
            _share_cloud_keys_to_peers(config)
            assert mock_write.call_count == 2
            calls = mock_write.call_args_list
            peer_names = {c[0][0] for c in calls}
            assert peer_names == {"wet-mcp", "mnemo-mcp"}

    def test_empty_config_skips_sharing(self):
        """No cloud keys in config -> no writes."""
        config = {"UNKNOWN_KEY": "value"}
        with patch("mcp_relay_core.storage.config_file.write_config") as mock_write:
            _share_cloud_keys_to_peers(config)
            mock_write.assert_not_called()

    def test_empty_values_filtered(self):
        """Empty-string values are filtered out."""
        config = {"GEMINI_API_KEY": "", "JINA_AI_API_KEY": ""}
        with patch("mcp_relay_core.storage.config_file.write_config") as mock_write:
            _share_cloud_keys_to_peers(config)
            mock_write.assert_not_called()

    def test_peer_write_failure_non_fatal(self):
        """Individual peer write failure doesn't crash."""
        config = {"GEMINI_API_KEY": "test-key"}
        with patch(
            "mcp_relay_core.storage.config_file.write_config",
            side_effect=OSError("disk full"),
        ):
            # Should not raise
            _share_cloud_keys_to_peers(config)

    def test_import_error_non_fatal(self):
        """Import error for write_config doesn't crash."""
        config = {"GEMINI_API_KEY": "test-key"}
        with patch(
            "mcp_relay_core.storage.config_file.write_config",
            side_effect=ImportError("no module"),
        ):
            _share_cloud_keys_to_peers(config)


# ---------------------------------------------------------------------------
# trigger_relay_setup
# ---------------------------------------------------------------------------


class TestTriggerRelaySetup:
    async def test_skips_when_already_configured(self):
        """Does not trigger relay when state is CONFIGURED."""
        set_state(CredentialState.CONFIGURED)
        url = await trigger_relay_setup()
        assert url is None

    async def test_skips_when_local(self):
        """Does not trigger relay when state is LOCAL."""
        set_state(CredentialState.LOCAL)
        url = await trigger_relay_setup()
        assert url is None

    async def test_force_overrides_configured(self):
        """force=True triggers relay even when CONFIGURED."""
        set_state(CredentialState.CONFIGURED)

        mock_session_info = MagicMock()
        mock_session_info.relay_url = "https://existing-session.example.com"

        with patch(
            "mcp_relay_core.acquire_session_lock",
            new_callable=AsyncMock,
            return_value=mock_session_info,
        ):
            url = await trigger_relay_setup(force=True)
            assert url == "https://existing-session.example.com"
            assert get_state() == CredentialState.SETUP_IN_PROGRESS

    async def test_reuses_existing_session(self):
        """Reuses existing session lock."""
        set_state(CredentialState.AWAITING_SETUP)

        mock_session_info = MagicMock()
        mock_session_info.relay_url = "https://existing.example.com/setup"

        with patch(
            "mcp_relay_core.acquire_session_lock",
            new_callable=AsyncMock,
            return_value=mock_session_info,
        ):
            url = await trigger_relay_setup()
            assert url == "https://existing.example.com/setup"
            assert get_setup_url() == "https://existing.example.com/setup"

    async def test_creates_new_session(self, monkeypatch):
        """Creates new relay session when no existing lock."""
        set_state(CredentialState.AWAITING_SETUP)

        mock_session = MagicMock()
        mock_session.session_id = "test-session-123"
        mock_session.relay_url = "https://new-session.example.com/setup#k=abc"

        with (
            patch(
                "mcp_relay_core.acquire_session_lock",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "mcp_relay_core.relay.client.create_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
            patch(
                "mcp_relay_core.write_session_lock",
                new_callable=AsyncMock,
            ) as mock_write_lock,
            patch("mcp_relay_core.try_open_browser") as mock_browser,
            patch("asyncio.create_task") as mock_task,
        ):
            url = await trigger_relay_setup()
            assert url == "https://new-session.example.com/setup#k=abc"
            assert get_setup_url() == url
            mock_write_lock.assert_called_once()
            mock_browser.assert_called_once_with(url)
            mock_task.assert_called_once()

    async def test_relay_setup_failure_returns_none(self, monkeypatch):
        """Relay setup failure returns None and resets state."""
        set_state(CredentialState.AWAITING_SETUP)

        with patch(
            "mcp_relay_core.acquire_session_lock",
            new_callable=AsyncMock,
            side_effect=ConnectionError("cannot connect"),
        ):
            url = await trigger_relay_setup()
            assert url is None
            assert get_state() == CredentialState.AWAITING_SETUP


# ---------------------------------------------------------------------------
# _poll_relay_background
# ---------------------------------------------------------------------------


class TestPollRelayBackground:
    async def test_poll_success_sets_configured(self):
        """Successful poll applies config and sets CONFIGURED."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        mock_session = MagicMock()
        mock_session.session_id = "sess-123"
        relay_base = "https://relay.example.com"
        config_data = {"GEMINI_API_KEY": "from-poll", "JINA_AI_API_KEY": "jina-poll"}

        with (
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                return_value=config_data,
            ),
            patch("mcp_relay_core.storage.config_file.write_config") as mock_write,
            patch(
                "mcp_relay_core.relay.client.send_message",
                new_callable=AsyncMock,
            ) as mock_send,
            patch(
                "mcp_relay_core.release_session_lock",
                new_callable=AsyncMock,
            ) as mock_release,
            patch(
                "better_code_review_graph.credential_state._share_cloud_keys_to_peers"
            ) as mock_share,
        ):
            await _poll_relay_background(relay_base, mock_session, timeout=10.0)
            assert get_state() == CredentialState.CONFIGURED
            mock_write.assert_called_once_with(SERVER_NAME, config_data)
            mock_share.assert_called_once_with(config_data)
            mock_send.assert_called_once()
            mock_release.assert_called_once_with(SERVER_NAME)

    async def test_poll_success_default_timeout(self):
        """Default timeout is 300s when timeout=None."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        mock_session = MagicMock()
        mock_session.session_id = "sess-456"

        with (
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                return_value={"GEMINI_API_KEY": "test"},
            ) as mock_poll,
            patch("mcp_relay_core.storage.config_file.write_config"),
            patch(
                "mcp_relay_core.relay.client.send_message",
                new_callable=AsyncMock,
            ),
            patch(
                "mcp_relay_core.release_session_lock",
                new_callable=AsyncMock,
            ),
            patch(
                "better_code_review_graph.credential_state._share_cloud_keys_to_peers"
            ),
        ):
            await _poll_relay_background(
                "https://relay.example.com", mock_session, timeout=None
            )
            # Check that poll_timeout defaulted to 300.0
            call_kwargs = mock_poll.call_args
            assert call_kwargs[1]["timeout_s"] == 300.0

    async def test_poll_send_message_failure_non_fatal(self):
        """send_message failure is non-fatal."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        mock_session = MagicMock()
        mock_session.session_id = "sess-789"

        with (
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                return_value={"GEMINI_API_KEY": "test"},
            ),
            patch("mcp_relay_core.storage.config_file.write_config"),
            patch(
                "mcp_relay_core.relay.client.send_message",
                new_callable=AsyncMock,
                side_effect=ConnectionError("send failed"),
            ),
            patch(
                "mcp_relay_core.release_session_lock",
                new_callable=AsyncMock,
            ),
            patch(
                "better_code_review_graph.credential_state._share_cloud_keys_to_peers"
            ),
        ):
            await _poll_relay_background(
                "https://relay.example.com", mock_session, timeout=10.0
            )
            # Should still be CONFIGURED despite send_message failure
            assert get_state() == CredentialState.CONFIGURED

    async def test_poll_session_no_id_skips_send(self):
        """Session without session_id skips send_message."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        # Session object without session_id attribute
        mock_session = MagicMock(spec=[])

        with (
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                return_value={"GEMINI_API_KEY": "test"},
            ),
            patch("mcp_relay_core.storage.config_file.write_config"),
            patch(
                "mcp_relay_core.relay.client.send_message",
                new_callable=AsyncMock,
            ) as mock_send,
            patch(
                "mcp_relay_core.release_session_lock",
                new_callable=AsyncMock,
            ),
            patch(
                "better_code_review_graph.credential_state._share_cloud_keys_to_peers"
            ),
        ):
            await _poll_relay_background(
                "https://relay.example.com", mock_session, timeout=10.0
            )
            assert get_state() == CredentialState.CONFIGURED
            mock_send.assert_not_called()

    async def test_poll_relay_skipped_sets_local(self):
        """RELAY_SKIPPED runtime error sets LOCAL mode."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        mock_session = MagicMock()

        with (
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("RELAY_SKIPPED"),
            ),
            patch("mcp_relay_core.set_local_mode") as mock_local,
        ):
            await _poll_relay_background(
                "https://relay.example.com", mock_session, timeout=10.0
            )
            assert get_state() == CredentialState.LOCAL
            mock_local.assert_called_once_with(SERVER_NAME)

    async def test_poll_relay_skipped_set_local_mode_failure(self):
        """set_local_mode failure on RELAY_SKIPPED is non-fatal."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        mock_session = MagicMock()

        with (
            patch(
                "mcp_relay_core.relay.client.poll_for_result",
                new_callable=AsyncMock,
                side_effect=RuntimeError("RELAY_SKIPPED"),
            ),
            patch(
                "mcp_relay_core.set_local_mode",
                side_effect=ImportError("no module"),
            ),
        ):
            await _poll_relay_background(
                "https://relay.example.com", mock_session, timeout=10.0
            )
            assert get_state() == CredentialState.LOCAL

    async def test_poll_other_runtime_error_resets(self):
        """Non-RELAY_SKIPPED RuntimeError resets to AWAITING_SETUP."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        mock_session = MagicMock()

        with patch(
            "mcp_relay_core.relay.client.poll_for_result",
            new_callable=AsyncMock,
            side_effect=RuntimeError("timed out"),
        ):
            await _poll_relay_background(
                "https://relay.example.com", mock_session, timeout=10.0
            )
            assert get_state() == CredentialState.AWAITING_SETUP

    async def test_poll_generic_exception_resets(self):
        """Generic exception resets to AWAITING_SETUP."""
        from better_code_review_graph.credential_state import _poll_relay_background

        set_state(CredentialState.SETUP_IN_PROGRESS)

        mock_session = MagicMock()

        with patch(
            "mcp_relay_core.relay.client.poll_for_result",
            new_callable=AsyncMock,
            side_effect=ConnectionError("network error"),
        ):
            await _poll_relay_background(
                "https://relay.example.com", mock_session, timeout=10.0
            )
            assert get_state() == CredentialState.AWAITING_SETUP
