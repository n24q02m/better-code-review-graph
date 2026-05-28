import sys
from unittest.mock import MagicMock

# Mock missing dependencies before importing anything from the package
mock_nx = MagicMock()
sys.modules["networkx"] = mock_nx
sys.modules["tree_sitter"] = MagicMock()
sys.modules["tree_sitter_language_pack"] = MagicMock()
sys.modules["alembic"] = MagicMock()
sys.modules["alembic.config"] = MagicMock()
sys.modules["alembic.command"] = MagicMock()
sys.modules["watchdog"] = MagicMock()
sys.modules["watchdog.observers"] = MagicMock()
sys.modules["watchdog.events"] = MagicMock()
sys.modules["mcp"] = MagicMock()
sys.modules["mcp.server"] = MagicMock()
sys.modules["mcp.server.fastmcp"] = MagicMock()
sys.modules["fastmcp"] = MagicMock()
sys.modules["qwen3_embed"] = MagicMock()
sys.modules["loguru"] = MagicMock()
sys.modules["n24q02m_mcp_core"] = MagicMock()
sys.modules["n24q02m_mcp_core.relay"] = MagicMock()
sys.modules["n24q02m_mcp_core.relay.tool_helpers"] = MagicMock()

import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

# Add src to sys.path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from better_code_review_graph.graph import GraphStats  # noqa: E402
from better_code_review_graph.tools import list_graph_stats  # noqa: E402


class TestListGraphStatsCoverage(unittest.TestCase):
    def test_list_graph_stats_populated(self):
        with (
            unittest.mock.patch(
                "better_code_review_graph.tools._get_store"
            ) as mock_get_store,
            unittest.mock.patch("better_code_review_graph.tools.init_backend"),
            unittest.mock.patch(
                "better_code_review_graph.tools.EmbeddingStore"
            ) as mock_emb_store_class,
            unittest.mock.patch(
                "better_code_review_graph.tools.get_db_path"
            ) as mock_get_db_path,
            unittest.mock.patch(
                "better_code_review_graph.tools.resolve_backend"
            ) as mock_resolve_backend,
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
                nodes_by_kind={"Function": 60, "Class": 40},
                edges_by_kind={"CALLS": 150, "CONTAINS": 50},
                languages=["python", "typescript"],
                files_count=10,
                last_updated="2023-10-27T10:00:00",
            )
            mock_store.get_stats.return_value = stats

            # Setup mock embedding store
            mock_emb_store = MagicMock()
            mock_emb_store.count.return_value = 50
            mock_emb_store_class.return_value = mock_emb_store

            mock_resolve_backend.return_value = "local"
            mock_get_db_path.return_value = Path("/tmp/fake.db")

            result = list_graph_stats("/fake/repo")

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["total_nodes"], 100)
            self.assertEqual(result["embeddings_count"], 50)
            self.assertIn("Graph statistics for test-repo:", result["summary"])
            self.assertIn("python, typescript", result["summary"])
            self.assertIn("2023-10-27T10:00:00", result["summary"])
            self.assertIn("Function: 60", result["summary"])
            self.assertIn("CALLS: 150", result["summary"])
            self.assertIn(
                "Embeddings: 50 nodes embedded (backend: local)", result["summary"]
            )

            mock_store.close.assert_called_once()
            mock_emb_store.close.assert_called_once()

    def test_list_graph_stats_empty(self):
        with (
            unittest.mock.patch(
                "better_code_review_graph.tools._get_store"
            ) as mock_get_store,
            unittest.mock.patch("better_code_review_graph.tools.init_backend"),
            unittest.mock.patch(
                "better_code_review_graph.tools.EmbeddingStore"
            ) as mock_emb_store_class,
            unittest.mock.patch(
                "better_code_review_graph.tools.get_db_path"
            ) as mock_get_db_path,
            unittest.mock.patch(
                "better_code_review_graph.tools.resolve_backend"
            ) as mock_resolve_backend,
        ):
            # Setup mock store
            mock_store = MagicMock()
            mock_root = MagicMock()
            mock_root.name = "empty-repo"
            mock_get_store.return_value = (mock_store, mock_root)

            # Setup mock stats
            stats = GraphStats(
                total_nodes=0,
                total_edges=0,
                nodes_by_kind={},
                edges_by_kind={},
                languages=[],
                files_count=0,
                last_updated=None,
            )
            mock_store.get_stats.return_value = stats

            # Setup mock embedding store
            mock_emb_store = MagicMock()
            mock_emb_store.count.return_value = 0
            mock_emb_store_class.return_value = mock_emb_store

            mock_resolve_backend.return_value = "cloud"
            mock_get_db_path.return_value = Path("/tmp/fake.db")

            result = list_graph_stats(None)

            self.assertEqual(result["status"], "ok")
            self.assertIn("Languages: none", result["summary"])
            self.assertIn("Last updated: never", result["summary"])
            self.assertIn(
                "Embeddings: 0 nodes embedded (backend: cloud)", result["summary"]
            )


if __name__ == "__main__":
    unittest.main()
