from pathlib import Path
from unittest.mock import patch

from better_code_review_graph.tools import _resolve_path_fallback


def test_resolve_path_fallback_success(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = "file.py"
    file_path = root / target
    file_path.write_text("content")

    node, path_target, error = _resolve_path_fallback(root, target, "file_summary")

    assert node is None
    # We expect the resolved string path
    assert path_target == str(file_path.resolve())
    assert error is None


def test_resolve_path_fallback_not_relative(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = "../outside.py"

    # We mock resolve because is_relative_to depends on it
    with patch.object(Path, "resolve") as mock_resolve:
        # First call is root.resolve(), second is full_target_raw.resolve()
        mock_resolve.side_effect = [root.resolve(), (tmp_path / "outside.py").resolve()]
        node, path_target, error = _resolve_path_fallback(root, target, "file_summary")

    assert node is None
    assert path_target == target
    assert error == {"status": "error", "summary": "Invalid target path"}


def test_resolve_path_fallback_raw_symlink(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = "link.py"

    with patch.object(Path, "is_symlink") as mock_is_symlink:
        # In the function:
        # full_target_raw.is_symlink() is checked if is_relative_to is True
        # full_target.is_symlink() is checked if full_target_raw.is_symlink() is False

        # We want full_target_raw.is_symlink() to be True
        # mock_is_symlink will be called for full_target_raw and full_target
        mock_is_symlink.side_effect = [True, False]
        node, path_target, error = _resolve_path_fallback(root, target, "file_summary")

    assert error == {"status": "error", "summary": "Invalid target path"}


def test_resolve_path_fallback_resolved_symlink(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = "file.py"

    with patch.object(Path, "is_symlink") as mock_is_symlink:
        # We want full_target.is_symlink() to be True
        mock_is_symlink.side_effect = [False, True]
        node, path_target, error = _resolve_path_fallback(root, target, "file_summary")

    assert error == {"status": "error", "summary": "Invalid target path"}


def test_resolve_path_fallback_os_error(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = "error.py"

    with patch.object(Path, "resolve", side_effect=OSError("boom")):
        node, path_target, error = _resolve_path_fallback(root, target, "file_summary")

    assert error == {"status": "error", "summary": "Invalid target path"}


def test_resolve_path_fallback_value_error(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = "error.py"

    with patch.object(Path, "resolve", side_effect=ValueError("boom")):
        node, path_target, error = _resolve_path_fallback(root, target, "file_summary")

    assert error == {"status": "error", "summary": "Invalid target path"}


def test_resolve_path_fallback_ignored_pattern(tmp_path):
    root = tmp_path / "repo"
    target = "file.py"
    node, path_target, error = _resolve_path_fallback(root, target, "unknown_pattern")
    assert node is None
    assert path_target is None
    assert error is None
