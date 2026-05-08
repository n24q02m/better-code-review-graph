from unittest.mock import MagicMock

from better_code_review_graph.tools import _list_kinds_in_graph


def test_list_kinds_in_graph_returns_empty_on_exception():
    """Verify that _list_kinds_in_graph returns an empty list when an exception occurs."""
    bad_store = MagicMock()
    # Mocking the execute method to raise an exception
    bad_store._conn.execute.side_effect = Exception("Database error")

    result = _list_kinds_in_graph(bad_store)

    assert result == []
