import sys
from unittest.mock import MagicMock, patch


# Mock dependencies before importing the module under test
class MockModule(MagicMock):
    def __getattr__(self, name):
        return MagicMock()


modules = [
    "networkx",
    "tree_sitter",
    "tree_sitter_language_pack",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "mcp",
    "mcp.server",
    "mcp.server.fastmcp",
    "fastmcp",
    "qwen3_embed",
    "cohere",
    "google.genai",
    "openai",
    "httpx",
    "pydantic_settings",
    "n24q02m_mcp_core",
    "n24q02m_mcp_core.storage",
    "n24q02m_mcp_core.storage.per_plugin_store",
    "pygments",
    "pygments.lexers",
    "pygments.formatters",
]

for mod in modules:
    sys.modules[mod] = MockModule()

from better_code_review_graph.tools import build_or_update_graph  # noqa: E402


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


if __name__ == "__main__":
    try:
        test_build_or_update_graph_full_rebuild_error()
        test_build_or_update_graph_incremental_update_error()
        print("All isolated tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        sys.exit(1)
