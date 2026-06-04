import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to sys.path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Mocking modules that might be missing or complex
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
    "qwen3_embed",
    "cohere",
    "google.genai",
    "openai",
    "httpx",
    "pydantic_settings",
    "n24q02m_mcp_core",
    "n24q02m_mcp_core.relay",
    "n24q02m_mcp_core.relay.tool_helpers",
    "n24q02m_mcp_core.storage",
    "n24q02m_mcp_core.storage.per_plugin_store",
    "pygments",
    "pygments.lexers",
    "pygments.formatters",
    "alembic",
    "alembic.config",
    "alembic.command",
]


class MockModule(MagicMock):
    def __getattr__(self, name):
        return MagicMock()


def _get_tools_module():
    mocks = {}
    for mod in modules_to_mock:
        if mod not in sys.modules:
            mocks[mod] = MockModule()

    with patch.dict(sys.modules, mocks):
        import better_code_review_graph.tools as tools_mod
        from better_code_review_graph.graph import GraphStats as stats_class

        return tools_mod, stats_class


tools, GraphStats = _get_tools_module()


def test_build_response_header_error_path():
    """Test that _build_response_header handles exceptions during EmbeddingStore initialization."""
    with (
        patch.object(tools, "init_backend") as mock_init,
        patch.object(tools, "EmbeddingStore") as mock_emb_store_class,
    ):
        mock_init.side_effect = Exception("Backend failure")

        # Test with db_path present
        header = tools._build_response_header(None, Path("/tmp/fake.db"))

        assert header["embeddings_count"] == 0
        assert header["keyword_only"] is True
        assert header["graph_last_updated"] is None

        # Test with EmbeddingStore raising exception
        mock_init.side_effect = None
        mock_init.return_value = MagicMock()
        mock_emb_store_class.side_effect = Exception("Store failure")

        header = tools._build_response_header(None, Path("/tmp/fake.db"))
        assert header["embeddings_count"] == 0
        assert header["keyword_only"] is True


def test_list_graph_stats_error_path():
    """Test that list_graph_stats handles exceptions during EmbeddingStore initialization."""
    with (
        patch.object(tools, "_get_store") as mock_get_store,
        patch.object(tools, "init_backend") as mock_init,
        patch.object(tools, "EmbeddingStore"),
        patch.object(tools, "get_db_path") as mock_get_db_path,
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
            nodes_by_kind={},
            edges_by_kind={},
            languages=[],
            files_count=10,
            last_updated=None,
        )
        mock_store.get_stats.return_value = stats
        mock_get_db_path.return_value = Path("/tmp/fake.db")

        # Simulate failure in EmbeddingStore
        mock_init.side_effect = Exception("Forced failure")

        try:
            result = tools.list_graph_stats("/fake/repo")
            # If it doesn't raise, check result
            assert "embeddings_count" in result
            # It should ideally be 0 or None if we add the try/except
            print("list_graph_stats handled the error (or we already fixed it)")
        except Exception as e:
            print(f"list_graph_stats FAILED as expected: {e}")
            raise


if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
