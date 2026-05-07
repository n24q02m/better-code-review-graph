from unittest.mock import MagicMock

from better_code_review_graph.tools import _list_kinds_in_graph


def test_list_kinds_in_graph_success():
    """Verify that _list_kinds_in_graph returns the correct kinds on success."""
    mock_store = MagicMock()
    mock_execute = mock_store._conn.execute.return_value
    mock_execute.fetchall.return_value = [{"kind": "Class"}, {"kind": "Function"}]

    result = _list_kinds_in_graph(mock_store)

    assert result == ["Class", "Function"]
    mock_store._conn.execute.assert_called_once_with(
        "SELECT DISTINCT kind FROM nodes ORDER BY kind"
    )


def test_list_kinds_in_graph_execute_exception():
    """Verify that _list_kinds_in_graph returns an empty list if execute() raises an exception."""
    mock_store = MagicMock()
    mock_store._conn.execute.side_effect = RuntimeError("SQL Error")

    result = _list_kinds_in_graph(mock_store)

    assert result == []


def test_list_kinds_in_graph_fetchall_exception():
    """Verify that _list_kinds_in_graph returns an empty list if fetchall() raises an exception."""
    mock_store = MagicMock()
    mock_execute = mock_store._conn.execute.return_value
    mock_execute.fetchall.side_effect = Exception("Fetch Error")

    result = _list_kinds_in_graph(mock_store)

    assert result == []


def test_list_kinds_in_graph_processing_exception():
    """Verify that _list_kinds_in_graph returns an empty list if an exception occurs during list comprehension."""
    mock_store = MagicMock()
    mock_execute = mock_store._conn.execute.return_value
    # Returning rows missing the 'kind' key will trigger a KeyError in the list comprehension
    mock_execute.fetchall.return_value = [{"not_kind": "foo"}]

    result = _list_kinds_in_graph(mock_store)

    assert result == []
