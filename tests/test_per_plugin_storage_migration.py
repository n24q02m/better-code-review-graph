"""Verify migration to PerPluginStore + cred persistence works."""


def test_loads_from_new_path(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from mcp_core.storage.per_plugin_store import PerPluginStore

    PerPluginStore("better-code-review-graph").save({"GEMINI_API_KEY": "fake-key"})
    from better_code_review_graph.credential_state import load_credentials

    assert load_credentials().get("GEMINI_API_KEY") == "fake-key"


def test_save_writes_to_new_path(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from better_code_review_graph.credential_state import save_credentials

    save_credentials({"GEMINI_API_KEY": "saved-key"})
    from mcp_core.storage.per_plugin_store import PerPluginStore

    assert PerPluginStore("better-code-review-graph").load().get("GEMINI_API_KEY") == "saved-key"


def test_clear_removes_new_path(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from better_code_review_graph.credential_state import clear_credentials, save_credentials

    save_credentials({"x": "y"})
    clear_credentials()
    from mcp_core.storage.per_plugin_store import PerPluginStore

    assert PerPluginStore("better-code-review-graph").load() is None
