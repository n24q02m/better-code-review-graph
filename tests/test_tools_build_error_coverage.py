from unittest.mock import MagicMock, patch

from better_code_review_graph.tools import build_or_update_graph


def test_build_or_update_graph_full_rebuild_error():
    """Test that build_or_update_graph handles errors during full build."""
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        mock_store = MagicMock()
        mock_get_store.return_value = (mock_store, MagicMock())

        with patch("better_code_review_graph.tools.full_build") as mock_full_build:
            mock_full_build.side_effect = Exception("Full build failed")

            result = build_or_update_graph(full_rebuild=True)

            assert result["status"] == "error"
            assert "Graph build/update failed: Full build failed" in result["error"]
            mock_store.close.assert_called_once()


def test_build_or_update_graph_incremental_update_error():
    """Test that build_or_update_graph handles errors during incremental update."""
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        mock_store = MagicMock()
        mock_get_store.return_value = (mock_store, MagicMock())

        with patch(
            "better_code_review_graph.tools.incremental_update"
        ) as mock_inc_update:
            mock_inc_update.side_effect = Exception("Incremental update failed")

            result = build_or_update_graph(full_rebuild=False)

            assert result["status"] == "error"
            assert (
                "Graph build/update failed: Incremental update failed"
                in result["error"]
            )
            mock_store.close.assert_called_once()
