import tempfile
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


class TestNPlusOneFix:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def _make_node(self, path, name, kind="Function"):
        return NodeInfo(
            kind=kind,
            name=name,
            file_path=path,
            line_start=1,
            line_end=10,
            language="python",
        )

    def test_get_nodes_by_files(self):
        # Setup nodes in multiple files
        self.store.upsert_node(self._make_node("/a.py", "func_a"))
        self.store.upsert_node(self._make_node("/b.py", "func_b"))
        self.store.upsert_node(self._make_node("/c.py", "func_c"))
        self.store.commit()

        # Fetch nodes for multiple files
        nodes = self.store.get_nodes_by_files(["/a.py", "/b.py"])
        assert len(nodes) == 2
        paths = {n.file_path for n in nodes}
        assert paths == {"/a.py", "/b.py"}

        # Test with duplicates
        nodes_dup = self.store.get_nodes_by_files(["/a.py", "/a.py", "/b.py"])
        assert len(nodes_dup) == 2

        # Test empty
        assert self.store.get_nodes_by_files([]) == []

        # Test non-existent
        assert self.store.get_nodes_by_files(["/missing.py"]) == []

    def test_get_impact_radius_regression(self):
        # Setup a simple dependency chain: /a.py -> /b.py
        self.store.upsert_node(self._make_node("/a.py", "/a.py", kind="File"))
        self.store.upsert_node(self._make_node("/a.py", "func_a"))
        self.store.upsert_node(self._make_node("/b.py", "/b.py", kind="File"))
        self.store.upsert_node(self._make_node("/b.py", "func_b"))

        self.store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::func_a",
                target="/b.py::func_b",
                file_path="/a.py",
                line=5,
            )
        )
        self.store.commit()

        # Verify impact radius works with new logic
        result = self.store.get_impact_radius(["/a.py"])

        # changed_nodes should include func_a and /a.py
        changed_qns = {n.qualified_name for n in result["changed_nodes"]}
        assert "/a.py::func_a" in changed_qns
        assert "/a.py" in changed_qns

        # impacted_nodes should include func_b
        impacted_qns = {n.qualified_name for n in result["impacted_nodes"]}
        assert "/b.py::func_b" in impacted_qns
