from unittest.mock import MagicMock

from better_code_review_graph.tools import _list_kinds_in_graph


def test_list_kinds_in_graph_error_path():
    """Cover the Exception branch in _list_kinds_in_graph (line 690)."""
    mock_store = MagicMock()
    mock_store._conn.execute.side_effect = Exception("DB Error")

    kinds = _list_kinds_in_graph(mock_store)
    assert kinds == []
