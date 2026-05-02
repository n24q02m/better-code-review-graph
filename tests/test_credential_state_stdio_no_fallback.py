"""Regression tests for stdio-pure credential resolution.

Per spec 2026-05-01-stdio-pure-http-multiuser.md §4.1 + OQ3, stdio mode MUST
NOT consult ``PerPluginStore`` or any cross-process credential cache. Stdio
= single-user pure local; env vars only. ``PerPluginStore`` may only be read
in HTTP mode (``--http`` / ``MCP_TRANSPORT=http`` / ``TRANSPORT_MODE=http``).

crg has optional cloud keys (GEMINI / OPENAI / JINA / COHERE) plus a local
ONNX embedding + FalkorDB fallback, so AWAITING_SETUP is an acceptable end
state for stdio mode without creds (graph build / search still work).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.credential_state import (
    CLOUD_KEYS,
    CredentialState,
    resolve_credential_state,
)


@pytest.fixture(autouse=True)
def _reset_module_state():
    import better_code_review_graph.credential_state as cs

    cs._state = CredentialState.AWAITING_SETUP
    cs._setup_url = None
    yield
    cs._state = CredentialState.AWAITING_SETUP
    cs._setup_url = None


@pytest.fixture
def _clean_env(monkeypatch):
    """Strip env vars that influence resolve_credential_state."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("TRANSPORT_MODE", raising=False)


@pytest.fixture
def _stdio_argv(monkeypatch):
    """Force stdio detection by stripping ``--http`` from argv."""
    monkeypatch.setattr("sys.argv", ["better-code-review-graph"])


@pytest.fixture
def _http_argv(monkeypatch):
    """Force HTTP detection via ``--http`` argv."""
    monkeypatch.setattr("sys.argv", ["better-code-review-graph", "--http"])


class TestStdioNoPerPluginStoreFallback:
    """Stdio mode MUST NOT read PerPluginStore (spec §4.1 + OQ3)."""

    def test_stdio_skips_perpluginstore_load(
        self, monkeypatch, _clean_env, _stdio_argv
    ):
        """Stdio mode: PerPluginStore.load() must NEVER be called."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_load = MagicMock(return_value={"GEMINI_API_KEY": "leaked"})
            mock_store_cls.return_value.load = mock_load
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
        mock_load.assert_not_called()
        assert result == CredentialState.AWAITING_SETUP

    def test_stdio_ignores_saved_creds_in_store(
        self, monkeypatch, _clean_env, _stdio_argv
    ):
        """Even if PerPluginStore has saved creds, stdio mode ignores them."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "should-not-be-loaded"
            }
            with patch("mcp_core.get_mode", return_value=None):
                result = resolve_credential_state()
        assert result == CredentialState.AWAITING_SETUP
        # Store creds did NOT bleed into env
        import os as _os

        assert _os.environ.get("GEMINI_API_KEY") != "should-not-be-loaded"

    def test_stdio_ignores_local_mode_marker(
        self, monkeypatch, _clean_env, _stdio_argv
    ):
        """Stdio mode bypasses ``mcp_core.get_mode`` -- it is HTTP-only state."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch("mcp_core.get_mode", return_value="local") as mock_get_mode:
                result = resolve_credential_state()
        mock_get_mode.assert_not_called()
        assert result == CredentialState.AWAITING_SETUP

    def test_stdio_env_var_still_works(self, monkeypatch, _clean_env, _stdio_argv):
        """Stdio mode: env vars are the canonical cred source -> CONFIGURED."""
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaStdioKey")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            result = resolve_credential_state()
        # PerPluginStore not even constructed when env var present (early return)
        assert result == CredentialState.CONFIGURED


class TestHttpModeKeepsFallback:
    """HTTP mode MUST still consult PerPluginStore + local marker."""

    def test_http_argv_reads_perpluginstore(self, monkeypatch, _clean_env, _http_argv):
        """``--http`` argv: PerPluginStore.load() is consulted as before."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "GEMINI_API_KEY": "from-store"
            }
            result = resolve_credential_state()
        mock_store_cls.return_value.load.assert_called_once()
        assert result == CredentialState.CONFIGURED

    def test_http_env_var_reads_perpluginstore(self, monkeypatch, _clean_env):
        """``MCP_TRANSPORT=http``: PerPluginStore consulted."""
        monkeypatch.setattr("sys.argv", ["better-code-review-graph"])
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "OPENAI_API_KEY": "from-store"
            }
            result = resolve_credential_state()
        mock_store_cls.return_value.load.assert_called_once()
        assert result == CredentialState.CONFIGURED

    def test_http_transport_mode_env_reads_perpluginstore(
        self, monkeypatch, _clean_env
    ):
        """``TRANSPORT_MODE=http``: PerPluginStore consulted."""
        monkeypatch.setattr("sys.argv", ["better-code-review-graph"])
        monkeypatch.setenv("TRANSPORT_MODE", "http")
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = {
                "JINA_AI_API_KEY": "from-store"
            }
            result = resolve_credential_state()
        mock_store_cls.return_value.load.assert_called_once()
        assert result == CredentialState.CONFIGURED

    def test_http_local_mode_marker_returns_local(
        self, monkeypatch, _clean_env, _http_argv
    ):
        """HTTP mode: ``mcp_core.get_mode`` 'local' marker -> LOCAL state."""
        with patch(
            "better_code_review_graph.credential_state.PerPluginStore"
        ) as mock_store_cls:
            mock_store_cls.return_value.load.return_value = None
            with patch("mcp_core.get_mode", return_value="local"):
                result = resolve_credential_state()
        assert result == CredentialState.LOCAL


class TestIsHttpModeDetection:
    """Direct unit tests for the ``_is_http_mode`` helper."""

    def test_no_flag_is_stdio(self, monkeypatch, _clean_env):
        from better_code_review_graph.credential_state import _is_http_mode

        monkeypatch.setattr("sys.argv", ["better-code-review-graph"])
        assert _is_http_mode() is False

    def test_argv_http_flag(self, monkeypatch, _clean_env):
        from better_code_review_graph.credential_state import _is_http_mode

        monkeypatch.setattr("sys.argv", ["better-code-review-graph", "--http"])
        assert _is_http_mode() is True

    def test_mcp_transport_http_env(self, monkeypatch, _clean_env):
        from better_code_review_graph.credential_state import _is_http_mode

        monkeypatch.setattr("sys.argv", ["better-code-review-graph"])
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        assert _is_http_mode() is True

    def test_transport_mode_http_env(self, monkeypatch, _clean_env):
        from better_code_review_graph.credential_state import _is_http_mode

        monkeypatch.setattr("sys.argv", ["better-code-review-graph"])
        monkeypatch.setenv("TRANSPORT_MODE", "http")
        assert _is_http_mode() is True

    def test_mcp_transport_stdio_env_is_stdio(self, monkeypatch, _clean_env):
        from better_code_review_graph.credential_state import _is_http_mode

        monkeypatch.setattr("sys.argv", ["better-code-review-graph"])
        monkeypatch.setenv("MCP_TRANSPORT", "stdio")
        assert _is_http_mode() is False
