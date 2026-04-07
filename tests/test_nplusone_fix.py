import pytest
from unittest.mock import MagicMock, patch
from better_code_review_graph.graph import GraphStore, GraphNode

def test_get_nodes_by_files_batching():
    # Setup mock connection
    mock_conn = MagicMock()
    store = GraphStore(":memory:")
    store._conn = mock_conn

    # Mock row to node conversion
    store._row_to_node = MagicMock(side_effect=lambda r: GraphNode(
        id=r["id"], kind="Function", name=r["name"], qualified_name=r["qualified_name"],
        file_path=r["file_path"], line_start=1, line_end=10, language="python",
        parent_name=None, params="[]", return_type="None", is_test=False,
        file_hash="hash", extra={}
    ))

    # Define some files
    files = ["file1.py", "file2.py", "file3.py"]

    # Mock return values for execute
    mock_conn.execute.return_value.fetchall.return_value = [
        {"id": 1, "name": "func1", "qualified_name": "file1.py::func1", "file_path": "file1.py", "extra": "{}"},
        {"id": 2, "name": "func2", "qualified_name": "file2.py::func2", "file_path": "file2.py", "extra": "{}"},
    ]

    results = store.get_nodes_by_files(files)

    # Verify execute was called with json_each pattern
    assert mock_conn.execute.called
    args, _ = mock_conn.execute.call_args
    assert "WHERE file_path IN (SELECT value FROM json_each(?))" in args[0]
    assert len(results) == 2

def test_get_impact_radius_uses_batch_fetch():
    store = GraphStore(":memory:")
    store.get_nodes_by_files = MagicMock(return_value=[])
    store._build_networkx_graph = MagicMock()

    store.get_impact_radius(["f1.py", "f2.py"])

    # Verify it called the batch method instead of looping with get_nodes_by_file
    store.get_nodes_by_files.assert_called_once_with(["f1.py", "f2.py"])
