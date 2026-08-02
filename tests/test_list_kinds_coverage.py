from unittest.mock import MagicMock

from better_code_review_graph.tools import _list_kinds_in_graph


def test_list_kinds_in_graph_success():
    """Verify that _list_kinds_in_graph returns the correct kinds on success."""
    mock_store = MagicMock()
    mock_store._conn.execute.return_value = [{"kind": "Class"}, {"kind": "Function"}]

    result = _list_kinds_in_graph(mock_store)

    assert result == ["Class", "Function"]
    mock_store._conn.execute.assert_called_once_with(
        "SELECT DISTINCT kind FROM nodes ORDER BY kind"
    )


def test_list_kinds_in_graph_execute_exception():
    """A failed execute() reports unknown (None), never an empty graph."""
    mock_store = MagicMock()
    mock_store._conn.execute.side_effect = RuntimeError("SQL Error")

    result = _list_kinds_in_graph(mock_store)

    assert result is None


def test_list_kinds_in_graph_iteration_exception():
    """Failed cursor iteration reports unknown (None), never an empty graph."""
    mock_store = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__iter__.side_effect = Exception("Iter Error")
    mock_store._conn.execute.return_value = mock_cursor

    result = _list_kinds_in_graph(mock_store)

    assert result is None


def test_list_kinds_in_graph_processing_exception():
    """A row missing 'kind' reports unknown (None), never an empty graph."""
    mock_store = MagicMock()
    # Returning rows missing the 'kind' key will trigger a KeyError in the list comprehension
    mock_store._conn.execute.return_value = [{"not_kind": "foo"}]

    result = _list_kinds_in_graph(mock_store)

    assert result is None
