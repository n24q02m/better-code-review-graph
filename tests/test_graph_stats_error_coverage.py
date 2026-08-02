from pathlib import Path
from unittest.mock import MagicMock, patch

from better_code_review_graph.tools import _build_response_header, _list_kinds_in_graph


def test_list_kinds_in_graph_exception_handled():
    mock_store = MagicMock()
    mock_store._conn.execute.side_effect = Exception("DB error")
    # None, not []: an empty list would claim the graph holds no nodes.
    assert _list_kinds_in_graph(mock_store) is None


def test_build_response_header_embedding_exception_handled():
    with patch("better_code_review_graph.tools.EmbeddingStore") as mock_emb:
        mock_emb.side_effect = Exception("Embedding error")
        header = _build_response_header(db_path=Path("/tmp/fake"), store=None)
        # None, not 0: 0 is documented advice to run `graph action=embed`,
        # which cannot fix a store that will not open.
        assert header["embeddings_count"] is None
        assert "Embedding error" in header["embeddings_error"]
        assert header["keyword_only"] is True


def test_build_response_header_metadata_exception_handled():
    mock_store = MagicMock()
    mock_store.get_metadata.side_effect = Exception("Metadata error")
    # emb_count will be 0 because we don't mock it to fail here, but let's just test metadata
    with patch("better_code_review_graph.tools.EmbeddingStore") as mock_emb:
        mock_emb.return_value.count.return_value = 10
        header = _build_response_header(db_path=Path("/tmp/fake"), store=mock_store)
        assert header["graph_last_updated"] is None
        assert header["embeddings_count"] == 10
