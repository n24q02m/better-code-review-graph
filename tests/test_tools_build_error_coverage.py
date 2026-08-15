import sys
from unittest.mock import MagicMock, patch

# Surgical mocking only during import to avoid poisoning CI environment
modules_to_mock = [
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
    "fastretrieval",
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


class MockModule(MagicMock):
    def __getattr__(self, name):
        return MagicMock()


def _get_build_or_update_graph():
    # If already available, just return it
    try:
        from better_code_review_graph.tools import build_or_update_graph

        return build_or_update_graph
    except (ImportError, ModuleNotFoundError):
        # Mock only the missing ones
        mocks = {}
        for mod in modules_to_mock:
            if mod not in sys.modules:
                mocks[mod] = MockModule()

        with patch.dict(sys.modules, mocks):
            from better_code_review_graph.tools import build_or_update_graph

            return build_or_update_graph


build_or_update_graph = _get_build_or_update_graph()


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
        import traceback

        traceback.print_exc()
        sys.exit(1)
