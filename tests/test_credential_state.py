"""Tests for credential_state module -- non-blocking credential state machine.

Covers: CredentialState enum, resolve_credential_state(), trigger_relay_setup(),
_poll_relay_background(), set_state(), reset_state(),
get_state(), get_setup_url().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from better_code_review_graph.credential_state import (
    CLOUD_KEYS,
    SERVER_NAME,
    CredentialState,
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
    cs._active_handle = None
    yield
    cs._state = CredentialState.AWAITING_SETUP
    cs._setup_url = None
    cs._active_handle = None


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
            patch("mcp_core.clear_mode") as mock_clear,
            patch(
                "better_code_review_graph.credential_state.PerPluginStore"
            ) as mock_store_cls,
        ):
            mock_store_cls.return_value.clear = MagicMock()
            reset_state()
            assert get_state() == CredentialState.AWAITING_SETUP
            assert get_setup_url() is None
            mock_clear.assert_called_once_with(SERVER_NAME)
            mock_store_cls.return_value.clear.assert_called_once()

    def test_reset_state_handles_import_error(self):
        """reset_state silently handles exceptions from relay core."""
        import better_code_review_graph.credential_state as cs

        cs._state = CredentialState.CONFIGURED
        cs._setup_url = "https://example.com/setup"

        with patch(
            "mcp_core.clear_mode",
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
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_config_file_sets_configured(self, monkeypatch, _clean_env):
        """Step 2: saved per-plugin store with cloud keys -> CONFIGURED + env injected."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "from-config",
                "JINA_AI_API_KEY": "jina-cfg",
            }
            result = resolve_credential_state()
            assert result == CredentialState.CONFIGURED
            assert monkeypatch.setenv  # env vars should have been set

    def test_config_file_injects_env(self, monkeypatch, _clean_env):
        """Config values are injected into environment."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "injected-from-config"
            }
            resolve_credential_state()
            assert (
                monkeypatch.setenv is not None
            )  # monkeypatch is active so env changes are safe

    def test_config_file_no_cloud_keys(self, monkeypatch, _clean_env):
        """Store with no cloud keys -> falls through."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {"UNKNOWN_KEY": "value"}
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_config_file_read_exception(self, monkeypatch, _clean_env):
        """Store read failure -> falls through silently."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.side_effect = ImportError("no store")
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_local_mode_marker(self, monkeypatch, _clean_env):
        """Step 3: local mode marker -> LOCAL."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch("mcp_core.get_mode", return_value="local"):
                result = resolve_credential_state()
                assert result == CredentialState.LOCAL

    def test_local_mode_marker_exception(self, monkeypatch, _clean_env):
        """get_mode exception -> falls through to AWAITING_SETUP."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch(
                "mcp_core.get_mode",
                side_effect=ImportError("no relay"),
            ):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_nothing_found_awaiting_setup(self, monkeypatch, _clean_env):
        """Step 4: nothing found -> AWAITING_SETUP."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP


# ---------------------------------------------------------------------------
# Credential isolation regression guard
# ---------------------------------------------------------------------------


class TestCredentialIsolation:
    """better-code-review-graph must not write to peer MCP servers' configs.

    Replaces the prior `_share_cloud_keys_to_peers` helper which propagated
    cloud keys to wet-mcp + mnemo-mcp. The transparent-bridge architecture
    mandates each server own its own credentials.
    """

    def test_no_share_helper_exists(self):
        import better_code_review_graph.credential_state as mod

        assert not hasattr(mod, "_share_cloud_keys_to_peers")


# ---------------------------------------------------------------------------
# trigger_relay_setup
# ---------------------------------------------------------------------------


class TestTriggerRelaySetup:
    """Tests for trigger_relay_setup -- local HTTP fallback (no remote relay)."""

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

    async def test_force_spawns_local_form(self):
        """force=True spawns a local credential form even when CONFIGURED."""
        set_state(CredentialState.CONFIGURED)

        mock_handle = MagicMock(host="127.0.0.1", port=52201)

        with (
            patch(
                "mcp_core.start_local_server_background",
                new_callable=AsyncMock,
                return_value=mock_handle,
                create=True,
            ) as mock_start,
            patch("mcp_core.try_open_browser"),
        ):
            url = await trigger_relay_setup(force=True)
            assert url == "http://127.0.0.1:52201/"
            assert get_state() == CredentialState.SETUP_IN_PROGRESS
            mock_start.assert_awaited_once()

    async def test_reuses_active_handle(self):
        """When an active handle already exists, reuse its URL."""
        import better_code_review_graph.credential_state as cs

        set_state(CredentialState.AWAITING_SETUP)
        cs._active_handle = MagicMock()
        cs._setup_url = "http://127.0.0.1:52202/"

        with patch(
            "mcp_core.start_local_server_background",
            new_callable=AsyncMock,
            create=True,
        ) as mock_start:
            url = await trigger_relay_setup()
            assert url == "http://127.0.0.1:52202/"
            mock_start.assert_not_awaited()

    async def test_creates_new_spawn(self):
        """AWAITING_SETUP with no handle -> spawn local form, open browser."""
        set_state(CredentialState.AWAITING_SETUP)

        mock_handle = MagicMock(host="127.0.0.1", port=52203)

        with (
            patch(
                "mcp_core.start_local_server_background",
                new_callable=AsyncMock,
                return_value=mock_handle,
                create=True,
            ) as mock_start,
            patch("mcp_core.try_open_browser") as mock_browser,
        ):
            url = await trigger_relay_setup()
            assert url == "http://127.0.0.1:52203/"
            assert get_setup_url() == url
            mock_start.assert_awaited_once()
            mock_browser.assert_called_once_with(url)

    async def test_relay_setup_failure_returns_none(self):
        """Relay setup failure returns None and resets state."""
        set_state(CredentialState.AWAITING_SETUP)

        with patch(
            "mcp_core.start_local_server_background",
            new_callable=AsyncMock,
            side_effect=RuntimeError("bind failed"),
            create=True,
        ):
            url = await trigger_relay_setup()
            assert url is None
            assert get_state() == CredentialState.AWAITING_SETUP


class TestSaveCredentials:
    def test_save_credentials_writes_config_and_applies_env(
        self, monkeypatch, _clean_env
    ):
        """save_credentials writes own config via PerPluginStore + applies env."""
        from better_code_review_graph.credential_state import save_credentials

        config = {"GEMINI_API_KEY": "save-test-key"}
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.save = MagicMock()
            result = save_credentials(config, {"sub": "test-sub"})
            assert result is None
            mock_store_cls.return_value.save.assert_called_once_with(config)
            assert get_state() == CredentialState.CONFIGURED
            import os as _os

            assert _os.environ.get("GEMINI_API_KEY") == "save-test-key"
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def test_save_credentials_multi_user_routes_to_per_sub_store(
        self, monkeypatch, tmp_path, _clean_env
    ):
        """When PUBLIC_URL is set, credentials must land in
        <CRG_DATA_DIR>/subs/<sub>/config.json -- never wet-mcp / mnemo-mcp."""
        from better_code_review_graph.credential_state import save_credentials

        monkeypatch.setenv("PUBLIC_URL", "https://crg.example.test")
        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))

        config = {"GEMINI_API_KEY": "user-a-key"}
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.save = MagicMock()
            result = save_credentials(config, {"sub": "user-a-sub"})

        assert result is None
        # Multi-user mode must NOT touch PerPluginStore (uses per-sub JSON directly).
        mock_store_cls.return_value.save.assert_not_called()
        assert get_state() == CredentialState.CONFIGURED
        # Key landed in per-sub bucket.
        per_sub_file = tmp_path / "subs" / "user-a-sub" / "config.json"
        assert per_sub_file.exists()
        import json

        assert json.loads(per_sub_file.read_text()) == config

    def test_save_credentials_multi_user_requires_sub(self, monkeypatch, _clean_env):
        """Multi-user mode without a SubjectContext sub is a hard error --
        silent-fallback to single-user would leak credentials across users."""
        import pytest

        from better_code_review_graph.credential_state import save_credentials

        monkeypatch.setenv("PUBLIC_URL", "https://crg.example.test")
        with pytest.raises(RuntimeError, match="SubjectContext"):
            save_credentials({"GEMINI_API_KEY": "k"}, None)
        with pytest.raises(RuntimeError, match="SubjectContext"):
            save_credentials({"GEMINI_API_KEY": "k"}, {})


class TestPerSubHelpers:
    """Cover the per-JWT-sub directory helpers used by remote multi-user mode."""

    def test_db_path_for_sub(self, monkeypatch, tmp_path):
        from better_code_review_graph.credential_state import db_path_for_sub

        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        path = db_path_for_sub("user-x")
        assert path == tmp_path / "subs" / "user-x" / "graph.db"
        # Parent dir is created eagerly so the SQLite open() succeeds.
        assert path.parent.exists()

    def test_read_for_sub_returns_empty_when_absent(self, monkeypatch, tmp_path):
        from better_code_review_graph.credential_state import read_for_sub

        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        assert read_for_sub("brand-new-sub") == {}

    def test_read_for_sub_roundtrips_stored_config(self, monkeypatch, tmp_path):
        from better_code_review_graph.credential_state import (
            read_for_sub,
            store_for_sub,
        )

        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        store_for_sub("user-y", {"GEMINI_API_KEY": "y-key"})
        assert read_for_sub("user-y") == {"GEMINI_API_KEY": "y-key"}
