import os

import pytest

from better_code_review_graph.credential_state import _sub_data_dir


def test_sub_data_dir_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    (tmp_path / "subs").mkdir(parents=True, exist_ok=True)

    # Valid sub
    valid_dir = _sub_data_dir("user123")
    assert valid_dir.is_relative_to(tmp_path / "subs")
    assert valid_dir.name == "user123"

    # Path traversal attempt
    with pytest.raises(ValueError, match="Invalid subject"):
        _sub_data_dir("../../../etc")

    with pytest.raises(ValueError, match="Invalid subject"):
        _sub_data_dir("some/../../dir")

    # Bypassing simple checks with legitimate-looking paths that resolve outside
    with pytest.raises(ValueError, match="Invalid subject"):
        _sub_data_dir("../subs/admin")

    # Special components
    for bad_sub in [".", "..", "", "/", "\\", "a/b", "a\\b"]:
        if bad_sub == "\\" and os.name != "nt":
            # On non-Windows, single backslash is just a char, but we block it anyway for portability
            pass
        with pytest.raises(ValueError, match="Invalid subject"):
            _sub_data_dir(bad_sub)
