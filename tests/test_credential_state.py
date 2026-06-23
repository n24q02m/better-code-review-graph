import os
from unittest.mock import patch

import pytest

from better_code_review_graph.credential_state import (
    CredentialState,
    _sub_data_dir,
    clear_credentials,
    config_value_for_current_request,
    credentials_for_current_request,
    db_path_for_sub,
    get_current_sub,
    get_setup_url,
    get_state,
    load_credentials,
    reset_state,
    resolve_credential_state,
    save_credentials,
    set_current_sub,
    set_state,
    store_for_sub,
)


@pytest.fixture
def _clean_env(monkeypatch):
    from better_code_review_graph.credential_state import CLOUD_KEYS

    for k in CLOUD_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("TRANSPORT_MODE", raising=False)
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("CRG_DATA_DIR", raising=False)
    reset_state()


class TestCredentialStateExtended:
    def test_get_setup_url(self):
        assert get_setup_url() is None

    def test_set_state(self):
        set_state(CredentialState.LOCAL)
        assert get_state() == CredentialState.LOCAL
        set_state(CredentialState.AWAITING_SETUP)

    def test_resolve_credential_state_skips_existing_env(self, monkeypatch, _clean_env):
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        monkeypatch.setenv("SOME_NON_CLOUD_CONFIG", "existing")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "from-store",
                "SOME_NON_CLOUD_CONFIG": "from-store",
            }
            with patch("mcp_core.get_mode", return_value=None):
                resolve_credential_state()
                assert os.environ["SOME_NON_CLOUD_CONFIG"] == "existing"
                assert os.environ["GEMINI_API_KEY"] == "from-store"

    def test_resolve_credential_state_store_exception(self, monkeypatch, _clean_env):
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.side_effect = Exception("store failed")
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_resolve_credential_state_get_mode_local(self, monkeypatch, _clean_env):
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch("mcp_core.get_mode", return_value="local"):
                result = resolve_credential_state()
                assert result == CredentialState.LOCAL

    def test_resolve_credential_state_get_mode_exception(self, monkeypatch, _clean_env):
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch("mcp_core.get_mode", side_effect=Exception("mode failed")):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP

    def test_load_credentials_wrappers(self):
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {"foo": "bar"}
            assert load_credentials("sub1") == {"foo": "bar"}
            mock_store_cls.assert_called_with("better-code-review-graph", "sub1")

            mock_store_cls.return_value.load.return_value = None
            assert load_credentials() == {}

    def test_clear_credentials_wrapper(self):
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            clear_credentials("sub2")
            mock_store_cls.return_value.clear.assert_called_once()

    def test_current_sub_management(self):
        set_current_sub("user-123")
        assert get_current_sub() == "user-123"
        set_current_sub(None)
        assert get_current_sub() is None

    def test_request_scoped_resolution(self, monkeypatch, tmp_path, _clean_env):
        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")

        # Stdio/Single-user
        set_current_sub(None)
        assert credentials_for_current_request()["GEMINI_API_KEY"] == "env-key"
        assert config_value_for_current_request("GEMINI_API_KEY") == "env-key"

        # Multi-user
        store_for_sub("u1", {"GEMINI_API_KEY": "sub-key"})
        set_current_sub("u1")
        try:
            assert credentials_for_current_request()["GEMINI_API_KEY"] == "sub-key"
            assert config_value_for_current_request("GEMINI_API_KEY") == "sub-key"
            assert config_value_for_current_request("MISSING") is None
        finally:
            set_current_sub(None)

    def test_db_path_for_sub(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        path = db_path_for_sub("u123")
        assert path.name == "graph.db"
        assert "u123" in str(path)

    def test_save_credentials_multi_user_no_sub(self, monkeypatch, _clean_env):
        monkeypatch.setenv("PUBLIC_URL", "https://remote")
        with pytest.raises(RuntimeError, match="sub required"):
            save_credentials({"k": "v"}, {})

    def test_sub_data_dir_validation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        for bad in ["..", "/", "a/b", ".", ""]:
            with pytest.raises(ValueError, match="Invalid subject"):
                _sub_data_dir(bad)

    def test_reset_state_handles_exceptions(self, _clean_env):
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.clear.side_effect = Exception("failed")
            # Should not raise
            reset_state()

    def test_resolve_credential_state_env_vars(self, monkeypatch, _clean_env):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        result = resolve_credential_state()
        assert result == CredentialState.CONFIGURED

    def test_resolve_credential_state_stdio_ignores_store(
        self, monkeypatch, _clean_env
    ):
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {"GEMINI_API_KEY": "key"}
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
                assert result == CredentialState.AWAITING_SETUP
                mock_store_cls.assert_not_called()

    def test_save_credentials_local(self, _clean_env):
        config = {"GEMINI_API_KEY": "key"}
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            with patch(
                "better_code_review_graph.relay_setup.apply_config"
            ) as mock_apply:
                save_credentials(config)
                mock_store_cls.return_value.save.assert_called_with(config)
                mock_apply.assert_called_with(config)
                assert get_state() == CredentialState.CONFIGURED

    def test_save_credentials_remote(self, monkeypatch, tmp_path, _clean_env):
        monkeypatch.setenv("PUBLIC_URL", "https://remote")
        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        config = {"GEMINI_API_KEY": "key"}
        save_credentials(config, {"sub": "u1"})
        assert get_state() == CredentialState.CONFIGURED
        assert (tmp_path / "subs" / "u1" / "config.json").exists()


class TestCredentialHelpersExtra:
    def test_get_setup_url(self):
        from better_code_review_graph.credential_state import get_setup_url

        assert get_setup_url() is None

    def test_load_credentials_wrappers(self):
        from better_code_review_graph.credential_state import load_credentials

        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {"foo": "bar"}
            assert load_credentials("sub1") == {"foo": "bar"}
            mock_store_cls.assert_called_with("better-code-review-graph", "sub1")

            mock_store_cls.return_value.load.return_value = None
            assert load_credentials() == {}

    def test_clear_credentials_wrapper(self):
        from better_code_review_graph.credential_state import clear_credentials

        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            clear_credentials("sub2")
            mock_store_cls.return_value.clear.assert_called_once()

    def test_current_sub_management(self):
        from better_code_review_graph.credential_state import (
            get_current_sub,
            set_current_sub,
        )

        set_current_sub("user-123")
        assert get_current_sub() == "user-123"
        set_current_sub(None)
        assert get_current_sub() is None

    def test_request_scoped_resolution_extra(self, monkeypatch, tmp_path, _clean_env):
        from better_code_review_graph.credential_state import (
            config_value_for_current_request,
            credentials_for_current_request,
            set_current_sub,
            store_for_sub,
        )

        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")

        # Stdio/Single-user
        set_current_sub(None)
        assert credentials_for_current_request()["GEMINI_API_KEY"] == "env-key"
        assert config_value_for_current_request("GEMINI_API_KEY") == "env-key"

        # Multi-user
        store_for_sub("u1", {"GEMINI_API_KEY": "sub-key"})
        set_current_sub("u1")
        try:
            assert credentials_for_current_request()["GEMINI_API_KEY"] == "sub-key"
            assert config_value_for_current_request("GEMINI_API_KEY") == "sub-key"
            assert config_value_for_current_request("MISSING") is None
        finally:
            set_current_sub(None)

    def test_reset_state_handles_exceptions_extra(self, _clean_env):
        from better_code_review_graph.credential_state import reset_state

        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.clear.side_effect = Exception("failed")
            # Should not raise
            reset_state()

    def test_resolve_credential_state_skips_existing_env_extra(
        self, monkeypatch, _clean_env
    ):
        from better_code_review_graph.credential_state import resolve_credential_state

        monkeypatch.setenv("MCP_TRANSPORT", "http")
        # Ensure no cloud keys in env to reach line 125
        # Set a NON-cloud key that is in both env and store
        monkeypatch.setenv("SOME_NON_CLOUD_CONFIG", "existing")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "from-store",
                "SOME_NON_CLOUD_CONFIG": "from-store",
            }
            with patch("mcp_core.get_mode", return_value=None):
                resolve_credential_state()
                import os as _os

                assert _os.environ["SOME_NON_CLOUD_CONFIG"] == "existing"
                assert _os.environ["GEMINI_API_KEY"] == "from-store"
