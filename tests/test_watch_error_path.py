import logging
from unittest.mock import MagicMock, patch

from better_code_review_graph.incremental import GraphUpdateHandler


def test_update_file_error_path(tmp_path, caplog):
    """Test that _update_file logs an error when _update_single_file fails."""
    repo_root = tmp_path
    sample_file = repo_root / "sample.py"
    sample_file.write_text("def foo(): pass")

    mock_store = MagicMock()
    mock_parser = MagicMock()

    handler = GraphUpdateHandler(
        repo_root=repo_root, store=mock_store, parser=mock_parser, ignore_patterns=[]
    )

    abs_path = str(sample_file)

    with patch(
        "better_code_review_graph.incremental._update_single_file",
        side_effect=Exception("Test Error"),
    ):
        with caplog.at_level(logging.ERROR):
            handler._update_file(abs_path)

    assert f"Error updating {abs_path}: Test Error" in caplog.text


def test_update_file_non_existent(tmp_path, caplog):
    """Test that _update_file returns early if file doesn't exist."""
    repo_root = tmp_path
    non_existent = repo_root / "missing.py"

    mock_store = MagicMock()
    mock_parser = MagicMock()
    handler = GraphUpdateHandler(
        repo_root=repo_root, store=mock_store, parser=mock_parser, ignore_patterns=[]
    )

    with caplog.at_level(logging.ERROR):
        handler._update_file(str(non_existent))

    assert len(caplog.records) == 0
    assert not mock_store.commit.called


def test_update_file_binary(tmp_path, caplog):
    """Test that _update_file returns early for binary files."""
    repo_root = tmp_path
    binary_file = repo_root / "data.bin"
    binary_file.write_bytes(b"hello\x00world")

    mock_store = MagicMock()
    mock_parser = MagicMock()
    handler = GraphUpdateHandler(
        repo_root=repo_root, store=mock_store, parser=mock_parser, ignore_patterns=[]
    )

    with caplog.at_level(logging.ERROR):
        handler._update_file(str(binary_file))

    assert len(caplog.records) == 0
    assert not mock_store.commit.called
