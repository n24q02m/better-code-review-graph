from better_code_review_graph.embeddings import EmbeddingStore
from better_code_review_graph.graph import GraphNode


class MockBackend:
    def __init__(self, name="mock"):
        self.name = name
        self.embed_calls = 0

    def embed_texts(self, texts, dimensions=None):
        self.embed_calls += 1
        return [[0.1] * 768 for _ in texts]


def make_node(i):
    return GraphNode(
        id=i,
        kind="Function",
        name=f"name{i}",
        qualified_name=f"node{i}",
        file_path="f.py",
        line_start=1,
        line_end=2,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash="hash",
        extra={},
    )


def test_embed_nodes_batching(tmp_path):
    db_path = tmp_path / "test.db"
    backend = MockBackend()
    store = EmbeddingStore(db_path, backend)

    nodes = [make_node(i) for i in range(10)]

    # Process in batches of 3
    # 10 nodes, batch_size=3 -> batches: [0,1,2], [3,4,5], [6,7,8], [9]
    count = store.embed_nodes(nodes, batch_size=3)

    assert count == 10
    assert backend.embed_calls == 4
    assert store.count() == 10


def test_embed_nodes_skips_already_embedded(tmp_path):
    db_path = tmp_path / "test.db"
    backend = MockBackend()
    store = EmbeddingStore(db_path, backend)

    nodes = [make_node(i) for i in range(10)]

    # First embed all
    store.embed_nodes(nodes, batch_size=10)
    assert backend.embed_calls == 1

    # Second call with same nodes should do nothing
    count = store.embed_nodes(nodes, batch_size=10)
    assert count == 0
    assert backend.embed_calls == 1  # No new calls to backend


def test_embed_nodes_partial_embedding(tmp_path):
    db_path = tmp_path / "test.db"
    backend = MockBackend()
    store = EmbeddingStore(db_path, backend)

    nodes = [make_node(i) for i in range(5)]

    # Embed first 3
    store.embed_nodes(nodes[:3], batch_size=10)
    assert backend.embed_calls == 1

    # Now embed all 5
    count = store.embed_nodes(nodes, batch_size=10)
    assert count == 2  # Only node3 and node4
    assert backend.embed_calls == 2  # One more call for the remaining 2


def test_embed_nodes_provider_change_triggers_reembedding(tmp_path):
    db_path = tmp_path / "test.db"

    # First provider
    backend1 = MockBackend(name="mock1")
    store1 = EmbeddingStore(db_path, backend1)
    nodes = [make_node(i) for i in range(10)]
    store1.embed_nodes(nodes, batch_size=10)
    assert backend1.embed_calls == 1
    store1.close()

    # Second provider
    backend2 = MockBackend(name="mock2")
    store2 = EmbeddingStore(db_path, backend2)
    count = store2.embed_nodes(nodes, batch_size=10)
    assert count == 10  # Should re-embed everything
    assert backend2.embed_calls == 1
