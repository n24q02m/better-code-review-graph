from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.tools import query_graph


@pytest.fixture
def mock_store_and_root(tmp_path):
    store = MagicMock()
    # Mocking these to ensure we fall through to _resolve_path_fallback
    store.get_node.return_value = None
    store.search_nodes.return_value = []

    # For _list_kinds_in_graph which might be called in _handle_not_found
    store._conn.execute.return_value = []

    return store, tmp_path


def test_query_graph_path_resolve_oserror(mock_store_and_root):
    store, root = mock_store_and_root
    with patch("better_code_review_graph.tools._get_store", return_value=(store, root)):
        with patch("pathlib.Path.resolve", side_effect=OSError("Mocked OSError")):
            result = query_graph(pattern="file_summary", target="some/path")

            assert result == {
                "status": "error",
                "summary": "Invalid target path",
            }


def test_query_graph_path_resolve_valueerror(mock_store_and_root):
    store, root = mock_store_and_root
    with patch("better_code_review_graph.tools._get_store", return_value=(store, root)):
        with patch("pathlib.Path.resolve", side_effect=ValueError("Mocked ValueError")):
            result = query_graph(pattern="file_summary", target="some/path")

            assert result == {
                "status": "error",
                "summary": "Invalid target path",
            }


def test_query_graph_path_not_relative(mock_store_and_root):
    store, root = mock_store_and_root
    with patch("better_code_review_graph.tools._get_store", return_value=(store, root)):
        # Using an absolute path that is not under root
        # /etc/passwd is a good candidate on unix-like systems
        result = query_graph(pattern="file_summary", target="/etc/passwd")

        assert result == {
            "status": "error",
            "summary": "Invalid target path",
        }


def test_query_graph_path_is_symlink(mock_store_and_root):
    store, root = mock_store_and_root

    # Create a real symlink
    target_file = root / "real_file.py"
    target_file.write_text("# content")
    link_file = root / "link_file.py"
    link_file.symlink_to(target_file)

    with patch("better_code_review_graph.tools._get_store", return_value=(store, root)):
        result = query_graph(pattern="file_summary", target="link_file.py")

        assert result == {
            "status": "error",
            "summary": "Invalid target path",
        }


def test_query_graph_path_fallback_importers_of_error(mock_store_and_root):
    store, root = mock_store_and_root
    with patch("better_code_review_graph.tools._get_store", return_value=(store, root)):
        with patch("pathlib.Path.resolve", side_effect=OSError("Mocked OSError")):
            result = query_graph(pattern="importers_of", target="some/path")

            assert result == {
                "status": "error",
                "summary": "Invalid target path",
            }
