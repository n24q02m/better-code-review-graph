from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import _handle_not_found


def test_handle_not_found_with_data(tmp_graph_store):
    """Test _handle_not_found with nodes present in the graph."""
    # Seed some data to have kinds in the graph
    tmp_graph_store.upsert_node(
        NodeInfo(
            kind="Function",
            name="my_func",
            file_path="test.py",
            line_start=1,
            line_end=10,
            language="python",
        )
    )
    tmp_graph_store.upsert_node(
        NodeInfo(
            kind="Class",
            name="MyClass",
            file_path="test.py",
            line_start=11,
            line_end=20,
            language="python",
        )
    )

    target = "missing_symbol"
    result = _handle_not_found(tmp_graph_store, target)

    assert result["status"] == "not_found"
    assert result["reason"] == "no_such_symbol"
    assert f"No node found matching {target!r}." in result["summary"]
    assert "Function" in result["indexed_kinds"]
    assert "Class" in result["indexed_kinds"]
    assert target in result["hint"]
    assert "file_path::Class.method" in result["hint"]


def test_handle_not_found_empty_graph(tmp_graph_store):
    """Test _handle_not_found with an empty graph."""
    target = "another_missing_symbol"
    result = _handle_not_found(tmp_graph_store, target)

    assert result["status"] == "not_found"
    assert result["indexed_kinds"] == []
    assert f"No node found matching {target!r}." in result["summary"]


def test_handle_not_found_store_error(tmp_graph_store):
    """Test _handle_not_found when store results in an error (e.g. closed connection)."""
    target = "error_symbol"
    tmp_graph_store.close()

    # The symbol genuinely was not found, so the status still holds -- but
    # the closed connection means we cannot also claim the graph is empty.
    result = _handle_not_found(tmp_graph_store, target)

    assert result["status"] == "not_found"
    assert result["indexed_kinds"] is None
    assert "not 'nothing indexed'" in result["indexed_kinds_error"]
