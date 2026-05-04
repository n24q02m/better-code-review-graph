from unittest.mock import MagicMock

import pytest


def test_sub_data_dir_valid_sub(tmp_path, monkeypatch):
    import sys

    sys.modules["mcp_core"] = MagicMock()
    sys.modules["mcp_core.storage"] = MagicMock()
    sys.modules["mcp_core.storage.per_plugin_store"] = MagicMock()

    from better_code_review_graph.credential_state import _sub_data_dir

    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    sub = "user123"
    result = _sub_data_dir(sub)
    expected_path = tmp_path / "subs" / sub
    assert result.resolve() == expected_path.resolve()
    assert result.exists()
    assert result.is_dir()


def test_sub_data_dir_path_traversal(tmp_path, monkeypatch):
    import sys

    sys.modules["mcp_core"] = MagicMock()
    sys.modules["mcp_core.storage"] = MagicMock()
    sys.modules["mcp_core.storage.per_plugin_store"] = MagicMock()

    from better_code_review_graph.credential_state import _sub_data_dir

    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    malicious_subs = [
        "../etc/passwd",
        "../../tmp",
        "user/../../etc",
        "/etc/passwd",
    ]
    for sub in malicious_subs:
        with pytest.raises(
            ValueError, match="Invalid subject identifier: path traversal detected"
        ):
            _sub_data_dir(sub)


def test_sub_data_dir_nested_valid(tmp_path, monkeypatch):
    import sys

    sys.modules["mcp_core"] = MagicMock()
    sys.modules["mcp_core.storage"] = MagicMock()
    sys.modules["mcp_core.storage.per_plugin_store"] = MagicMock()

    from better_code_review_graph.credential_state import _sub_data_dir

    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    sub = "group/user"
    result = _sub_data_dir(sub)
    expected_path = tmp_path / "subs" / "group" / "user"
    assert result.resolve() == expected_path.resolve()
    assert result.exists()
    assert result.is_dir()
