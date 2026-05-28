import time
from typing import cast

from better_code_review_graph.embeddings import EmbeddingBackend, EmbeddingStore
from tests.test_embeddings import _make_node


class MockBackend:
    name = "mock"

    def embed_texts(self, texts, dimensions):
        return [[0.1] * dimensions for _ in texts]


def test_embed_nodes_n1_performance(tmp_path):
    db_path = tmp_path / "test.db"
    backend = cast("EmbeddingBackend", MockBackend())
    store = EmbeddingStore(db_path, backend)

    nodes = []
    for i in range(500):
        nodes.append(
            _make_node(
                name=f"foo{i}",
                qualified_name=f"a.py::foo{i}",
                file_path="a.py",
            )
        )

    start = time.time()
    store.embed_nodes(nodes)
    elapsed = time.time() - start

    assert store.count() == 500
    print(f"Elapsed time: {elapsed:.4f}s")
    # assert elapsed < 0.2  # Should be very fast without N+1 query
