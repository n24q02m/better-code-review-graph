from unittest.mock import MagicMock, patch
from better_code_review_graph.tools import _list_kinds_in_graph, _build_response_header

def test_list_kinds_in_graph_exception_handled():
    mock_store = MagicMock()
    mock_store._conn.execute.side_effect = Exception("DB error")
    assert _list_kinds_in_graph(mock_store) == []

def test_build_response_header_embedding_exception_handled():
    with patch("better_code_review_graph.tools.EmbeddingStore") as mock_emb:
        mock_emb.side_effect = Exception("Embedding error")
        header = _build_response_header(db_path="/tmp/fake", store=None)
        assert header["embeddings_count"] == 0
        assert header["keyword_only"] is True

def test_build_response_header_metadata_exception_handled():
    mock_store = MagicMock()
    mock_store.get_metadata.side_effect = Exception("Metadata error")
    # emb_count will be 0 because we don't mock it to fail here, but let's just test metadata
    with patch("better_code_review_graph.tools.EmbeddingStore") as mock_emb:
        mock_emb.return_value.count.return_value = 10
        header = _build_response_header(db_path="/tmp/fake", store=mock_store)
        assert header["graph_last_updated"] is None
        assert header["embeddings_count"] == 10
