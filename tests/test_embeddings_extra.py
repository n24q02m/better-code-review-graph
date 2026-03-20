"""Extra embedding tests to cover edge cases."""

from __future__ import annotations

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
