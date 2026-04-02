"""Extra embedding tests to cover edge cases."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

from better_code_review_graph.embeddings import EmbeddingStore, embed_all_nodes
from better_code_review_graph.graph import GraphNode, GraphStore


def _make_node(**kwargs) -> GraphNode:
    defaults = {
        "id": 1,
        "kind": "Function",
        "name": "test",
        "qualified_name": "f.py::test",
        "file_path": "f.py",
        "line_start": 1,
        "line_end": 5,
        "language": "python",
        "parent_name": None,
        "params": None,
        "return_type": None,
        "is_test": False,
        "file_hash": None,
        "extra": {},
    }
    defaults.update(kwargs)
    return GraphNode(**defaults)


class TestEmbeddingStoreNoneBackend:
    def test_backend_name_none(self, tmp_path):
        db = tmp_path / "test.db"
        store = EmbeddingStore(db, backend=None)
        assert store._get_backend_name() == "none"
        assert store.available is False
        store.close()

    def test_embed_nodes_no_backend(self, tmp_path):
        db = tmp_path / "test.db"
        store = EmbeddingStore(db, backend=None)
        node = _make_node()
        result = store.embed_nodes([node])
        assert result == 0
        store.close()

    def test_search_no_backend(self, tmp_path):
        db = tmp_path / "test.db"
        store = EmbeddingStore(db, backend=None)
        result = store.search("query")
        assert result == []
        store.close()

    def test_embed_all_nodes_no_backend(self, tmp_path):
        db = tmp_path / "graph.db"
        graph = GraphStore(str(db))
        emb = EmbeddingStore(db, backend=None)
        result = embed_all_nodes(graph, emb)
        assert result == 0
        emb.close()
        graph.close()


class TestEmbeddingStoreMigration:
    def test_migration_operational_error(self, tmp_path):
        """Test that missing provider column triggers ALTER TABLE migration."""
        db_path = tmp_path / "migration.db"

        # We must patch where it's USED, which is better_code_review_graph.embeddings
        with patch("better_code_review_graph.embeddings.sqlite3") as mock_sqlite:
            # Re-expose OperationalError so the 'except' block works
            mock_sqlite.OperationalError = sqlite3.OperationalError

            mock_conn = MagicMock()
            mock_sqlite.connect.return_value = mock_conn

            def side_effect(sql, *args, **kwargs):
                if "SELECT provider FROM embeddings" in sql:
                    raise sqlite3.OperationalError("no such column: provider")
                return MagicMock()

            mock_conn.execute.side_effect = side_effect

            # Initialize store
            store = EmbeddingStore(db_path)

            # Verify ALTER TABLE was called
            executed_queries = [call[0][0] for call in mock_conn.execute.call_args_list]
            assert any(
                "ALTER TABLE embeddings ADD COLUMN provider" in q
                for q in executed_queries
            )

            # Verify commit was called
            assert mock_conn.commit.called

            store.close()
