import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from better_code_review_graph.embeddings import EmbeddingStore
from better_code_review_graph.graph import GraphNode

def _make_node(name="foo", qualified_name="a.py::foo", file_path="a.py", kind="Function"):
    return GraphNode(
        id=1,
        kind=kind,
        name=name,
        qualified_name=qualified_name,
        file_path=file_path,
        line_start=1,
        line_end=10,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash="hash",
        extra={}
    )

class TestEmbeddingStoreError:
    def test_embed_nodes_handles_exception(self, tmp_path, caplog):
        db = tmp_path / "graph.db"
        backend = MagicMock()
        backend.name = "mock_backend"
        backend.embed_texts.side_effect = Exception("Simulated embedding failure")

        store = EmbeddingStore(db, backend)

        nodes = [_make_node()]

        # Should return 0 and log the error
        count = store.embed_nodes(nodes)

        assert count == 0
        assert "Failed to embed nodes: Simulated embedding failure" in caplog.text
        store.close()
