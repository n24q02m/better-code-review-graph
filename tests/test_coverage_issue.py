from unittest.mock import patch

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import get_review_context


@pytest.fixture
def repo_with_invalid_file(tmp_path):
    (tmp_path / ".git").mkdir()
    crg_dir = tmp_path / ".code-review-graph"
    crg_dir.mkdir()

    # Create a file with invalid UTF-8 bytes
    bad_file = tmp_path / "bad_encoding.py"
    bad_file.write_bytes(b"\xff\xfe\xfd")

    # Create a normal file
    good_file = tmp_path / "good.py"
    good_file.write_text("def hello(): pass")

    # Seed graph
    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))

    abs_bad = str(bad_file)
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_bad,
            file_path=abs_bad,
            line_start=1,
            line_end=1,
            language="python",
        )
    )
    store.close()
    return tmp_path


def test_get_review_context_unicode_decode_error(repo_with_invalid_file):
    # Test that invalid UTF-8 triggers (could not read file)
    result = get_review_context(
        changed_files=["bad_encoding.py"], repo_root=str(repo_with_invalid_file)
    )

    assert result["status"] == "ok"
    assert (
        result["context"]["source_snippets"]["bad_encoding.py"]
        == "(could not read file)"
    )


def test_get_review_context_os_error(repo_with_invalid_file):
    # Mock read_text to raise OSError (e.g. PermissionError)
    with patch(
        "pathlib.Path.read_text", side_effect=PermissionError("Permission denied")
    ):
        result = get_review_context(
            changed_files=["good.py"], repo_root=str(repo_with_invalid_file)
        )

    assert result["status"] == "ok"
    assert result["context"]["source_snippets"]["good.py"] == "(could not read file)"
