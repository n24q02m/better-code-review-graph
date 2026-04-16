import tempfile
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo


class TestGraphGetEdgesByTargets:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_get_edges_by_targets_empty(self):
        assert self.store.get_edges_by_targets([]) == []

    def test_get_edges_by_targets_basic(self):
        # Setup edges
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a", target="b", file_path="f.py", line=1)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="c", target="d", file_path="f.py", line=2)
        )
        self.store.commit()

        edges = self.store.get_edges_by_targets(["b", "d"])
        assert len(edges) == 2
        targets = {e.target_qualified for e in edges}
        assert targets == {"b", "d"}

    def test_get_edges_by_targets_deduplication(self):
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a", target="b", file_path="f.py", line=1)
        )
        self.store.commit()

        # Requesting "b" twice should still return only one edge
        edges = self.store.get_edges_by_targets(["b", "b"])
        assert len(edges) == 1
        assert edges[0].target_qualified == "b"

    def test_get_edges_by_targets_multiple_sources(self):
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a1", target="b", file_path="f.py", line=1)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a2", target="b", file_path="f.py", line=2)
        )
        self.store.commit()

        edges = self.store.get_edges_by_targets(["b"])
        assert len(edges) == 2
        sources = {e.source_qualified for e in edges}
        assert sources == {"a1", "a2"}

    def test_get_edges_by_targets_batching(self):
        # Create 500 edges with unique targets
        target_names = [f"target_{i}" for i in range(500)]
        for i, target in enumerate(target_names):
            self.store.upsert_edge(
                EdgeInfo(
                    kind="CALLS",
                    source=f"source_{i}",
                    target=target,
                    file_path="f.py",
                    line=i,
                )
            )
        self.store.commit()

        edges = self.store.get_edges_by_targets(target_names)
        assert len(edges) == 500
        targets = {e.target_qualified for e in edges}
        assert len(targets) == 500
        assert "target_0" in targets
        assert "target_499" in targets
