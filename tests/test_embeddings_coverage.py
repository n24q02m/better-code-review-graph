import hashlib
import logging
from unittest.mock import MagicMock

from better_code_review_graph.embeddings import (
    EmbeddingStore,
    _encode_vector,
    _node_to_text,
)
from better_code_review_graph.graph import GraphNode


def _make_node(name, qualified_name, kind="Function", file_path="test.py"):
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
        file_hash=None,
        extra={},
    )


def test_embed_nodes_exception_handling(tmp_path, caplog):
    db = tmp_path / "graph.db"
    backend = MagicMock()
    # Mock embed_texts to raise an exception
    backend.embed_texts.side_effect = Exception("Embedding failed")
    backend.name = "mock"

    store = EmbeddingStore(db, backend)

    nodes = [_make_node("foo", "test.py::foo")]

    # Capture logs
    with caplog.at_level(logging.ERROR):
        count = store.embed_nodes(nodes)

    assert count == 0
    assert "Failed to embed nodes: Embedding failed" in caplog.text
    store.close()


def test_embed_nodes_batch_fetching(tmp_path):
    """Test that embed_nodes correctly uses batch fetching and filtering."""
    db = tmp_path / "graph.db"
    backend = MagicMock()
    # Return a list of lists (vectors)
    backend.embed_texts.return_value = [[0.1] * 768]
    backend.name = "mock"

    store = EmbeddingStore(db, backend)

    # 1. Insert an existing embedding
    node1 = _make_node("foo", "test.py::foo")
    blob = _encode_vector([0.1] * 768)
    text = _node_to_text(node1)
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    store._conn.execute(
        "INSERT INTO embeddings (qualified_name, vector, text_hash, provider) VALUES (?, ?, ?, ?)",
        (node1.qualified_name, blob, text_hash, "mock"),
    )
    store._conn.commit()

    # 2. Try to embed node1 (should be skipped) and node2 (should be embedded)
    node2 = _make_node("bar", "test.py::bar")
    nodes = [node1, node2]

    count = store.embed_nodes(nodes)

    assert count == 1
    # Verify backend was only called for node2
    backend.embed_texts.assert_called_once()
    texts_called = backend.embed_texts.call_args[0][0]
    assert len(texts_called) == 1
    assert "bar" in texts_called[0]

    store.close()
