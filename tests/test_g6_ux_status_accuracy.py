"""G6 UX accuracy, re-anchored for hull cells (WP2 de-host).

Original bug: setup_status reported stale ambient credential state. Under the
hull surface the same class of bug would be: setup_status reporting a cell as
configured because of stray legacy provider env vars, or leaking key material.
setup_status must derive per-task cell status ONLY from the instance config
(config.toml + HULL_<TASK>_API_KEY env), and never return secrets.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest


def _call_config_setup_status_sync() -> dict[str, Any]:
    from better_code_review_graph.server import config

    return asyncio.run(config(action="setup_status"))


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
    for k in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "JINA_AI_API_KEY",
        "OPENAI_API_KEY",
        "COHERE_API_KEY",
        "CO_API_KEY",
        "HULL_CHAT_API_KEY",
        "HULL_EMBED_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)


class TestSetupStatusDerivesFromInstanceConfig:
    """setup_status reflects the instance config cells, nothing ambient."""

    def test_stray_legacy_env_keys_do_not_configure_cells(self):
        """Legacy provider env vars must not make any cell look configured."""
        os.environ["GEMINI_API_KEY"] = "ambient-legacy"
        try:
            result = _call_config_setup_status_sync()
        finally:
            del os.environ["GEMINI_API_KEY"]

        assert result["state"] == "local"
        assert all(not c["configured"] for c in result["cells"].values())

    def test_env_key_configures_the_chat_cell(self, tmp_path):
        """HULL_CHAT_API_KEY + config base_url/model => chat cell configured."""
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            '[models.chat]\nbase_url = "https://openrouter.ai/api/v1"\n'
            'api_key = ""\nmodel = "z-ai/glm-5.3-flash"\n',
            encoding="utf-8",
        )
        os.environ["HULL_CHAT_API_KEY"] = "sk-env"
        try:
            result = _call_config_setup_status_sync()
        finally:
            del os.environ["HULL_CHAT_API_KEY"]

        assert result["state"] == "configured"
        assert result["cells"]["chat"]["configured"] is True
        assert result["cells"]["chat"]["model"] == "z-ai/glm-5.3-flash"
        assert result["cells"]["embed"]["configured"] is False

    def test_config_file_key_configures_without_env(self, tmp_path):
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            '[models.embed]\nbase_url = "https://api.cohere.com/v1"\n'
            'api_key = "sk-file"\nmodel = "voyage-4-lite"\n',
            encoding="utf-8",
        )
        result = _call_config_setup_status_sync()

        assert result["cells"]["embed"]["configured"] is True

    def test_response_includes_auth_mode_and_config_dir(self, tmp_path):
        result = _call_config_setup_status_sync()
        assert result["auth_mode"] == "no-auth"
        assert result["config_dir"] == str(tmp_path / "cfg")
        assert isinstance(result["cells"], dict)

    def test_response_never_contains_api_key_material(self, tmp_path):
        """G6-class accuracy: the status surface must never leak key material."""
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            '[models.chat]\nbase_url = "https://openrouter.ai/api/v1"\n'
            'api_key = "sk-secret-value"\nmodel = "m"\n',
            encoding="utf-8",
        )
        result = _call_config_setup_status_sync()

        assert "sk-secret-value" not in str(result)
