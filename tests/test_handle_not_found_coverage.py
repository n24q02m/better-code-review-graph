from unittest.mock import MagicMock

from better_code_review_graph.tools import _handle_not_found


def test_handle_not_found_output():
    """Verify the output of _handle_not_found."""
    mock_store = MagicMock()
    # Mocking _list_kinds_in_graph behavior (it calls store._conn.execute)
    mock_store._conn.execute.return_value = [{"kind": "Class"}, {"kind": "Function"}]

    target = "NonExistentSymbol"
    result = _handle_not_found(mock_store, target)

    assert result["status"] == "not_found"
    assert result["reason"] == "no_such_symbol"
    assert f"No node found matching '{target}'." in result["summary"]
    assert result["indexed_kinds"] == ["Class", "Function"]
    assert f"Symbol '{target}' not indexed in graph." in result["hint"]
    assert (
        "Verify name spelling or pass a qualified form ('file_path::Class.method')."
        in result["hint"]
    )
