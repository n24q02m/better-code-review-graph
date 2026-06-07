from pathlib import Path
from unittest.mock import MagicMock, patch

from better_code_review_graph.graph import GraphStats
from better_code_review_graph.tools import _build_response_header, list_graph_stats


def test_build_response_header_embedding_error():
    """Verify that _build_response_header handles EmbeddingStore errors."""
    with patch("better_code_review_graph.tools.EmbeddingStore") as mock_emb_store:
        # Simulate exception during initialization or any method
        mock_emb_store.side_effect = Exception("DB Corrupt")

        # We need a dummy db_path so it enters the try block
        h = _build_response_header(None, Path("/tmp/dummy.db"))

        assert h["embeddings_count"] == 0
        assert h["keyword_only"] is True


def test_list_graph_stats_embedding_error():
    """Verify that list_graph_stats handles EmbeddingStore errors."""
    with (
        patch("better_code_review_graph.tools._get_store") as mock_get_store,
        patch("better_code_review_graph.tools.EmbeddingStore") as mock_emb_store,
        patch("better_code_review_graph.tools.get_db_path") as mock_get_db_path,
        patch("better_code_review_graph.tools.init_backend"),
    ):
        # Setup mock store
        mock_store = MagicMock()
        mock_root = MagicMock()
        mock_root.name = "test-repo"
        mock_get_store.return_value = (mock_store, mock_root)

        # Setup mock stats
        stats = GraphStats(
            total_nodes=100,
            total_edges=200,
            nodes_by_kind={"Function": 60},
            edges_by_kind={"CALLS": 150},
            languages=["python"],
            files_count=10,
            last_updated="2023-10-27T10:00:00",
        )
        mock_store.get_stats.return_value = stats

        mock_get_db_path.return_value = Path("/tmp/fake.db")

        # Simulate exception in EmbeddingStore
        mock_emb_store.side_effect = Exception("Backend failure")

        result = list_graph_stats("/fake/repo")

        assert result["status"] == "ok"
        assert result["embeddings_count"] is None
        assert "Graph statistics for test-repo:" in result["summary"]
        # Ensure no "Embeddings:" line in summary since it crashed before appending
        assert "Embeddings:" not in result["summary"]

        mock_store.close.assert_called_once()
