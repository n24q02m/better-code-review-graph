import json
from unittest.mock import patch

from better_code_review_graph.server import config


def test_cache_clear_get_store_value_error():
    """Test config(action='cache_clear') when _get_store raises ValueError."""
    with patch(
        "better_code_review_graph.tools._get_store",
        side_effect=ValueError("No repo found"),
    ):
        result = json.loads(config.fn(action="cache_clear"))
        assert result["status"] == "cache cleared"
        assert result["embeddings_removed"] == 0


def test_cache_clear_embedding_store_runtime_error(tmp_path):
    """Test config(action='cache_clear') when EmbeddingStore raises RuntimeError."""
    with (
        patch(
            "better_code_review_graph.server.EmbeddingStore",
            side_effect=RuntimeError("Store initialization failed"),
        ),
        patch("better_code_review_graph.tools._get_store") as mock_get_store,
    ):
        # Mock _get_store to return a dummy store and root
        from unittest.mock import MagicMock

        mock_store = MagicMock()
        mock_get_store.return_value = (mock_store, tmp_path)

        result = json.loads(config.fn(action="cache_clear"))
        assert result["status"] == "cache cleared"
        assert result["embeddings_removed"] == 0
        # Ensure the outer store was closed
        mock_store.close.assert_called_once()
