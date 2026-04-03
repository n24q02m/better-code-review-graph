import tempfile
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


class TestGraphStoreExtra:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_get_edges_among_large_batch(self):
        """Verify get_edges_among works correctly with more than batch_size (450) names."""
        num_nodes = 600
        qns = [f"file.py::node_{i}" for i in range(num_nodes)]

        # Create edges between node_i and node_{i+1}
        for i in range(num_nodes - 1):
            self.store.upsert_edge(
                EdgeInfo(
                    kind="CALLS",
                    source=qns[i],
                    target=qns[i + 1],
                    file_path="file.py",
                    line=i,
                )
            )
        self.store.commit()

        # Query for all edges among all nodes
        results = self.store.get_edges_among(set(qns))

        # Should find all 599 edges
        assert len(results) == num_nodes - 1

        # Verify a sample
        sources = {e.source_qualified for e in results}
        assert "file.py::node_0" in sources
        assert f"file.py::node_{num_nodes - 2}" in sources

    def test_get_nodes_by_qualified_names_large_batch(self):
        """Verify get_nodes_by_qualified_names works correctly with large batches."""
        num_nodes = 600
        qns = []
        for i in range(num_nodes):
            qn = f"file.py::node_{i}"
            qns.append(qn)
            self.store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=f"node_{i}",
                    file_path="file.py",
                    line_start=i,
                    line_end=i + 1,
                )
            )
        self.store.commit()

        results = self.store.get_nodes_by_qualified_names(qns)
        assert len(results) == num_nodes

        result_qns = {n.qualified_name for n in results}
        assert "file.py::node_0" in result_qns
        assert f"file.py::node_{num_nodes - 1}" in result_qns
