import tempfile
import time
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo


class TestSearchEdgesByTargetNames:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_search_edges_by_target_names_empty(self):
        assert self.store.search_edges_by_target_names([]) == []

    def test_search_edges_by_target_names_basic(self):
        # Setup edges
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a", target="b", file_path="f.py", line=1)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="c", target="d", file_path="f.py", line=2)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="OTHER", source="e", target="b", file_path="f.py", line=3)
        )
        self.store.commit()

        # Default kind is CALLS
        edges = self.store.search_edges_by_target_names(["b", "d"])
        assert len(edges) == 2
        targets = {e.target_qualified for e in edges}
        assert targets == {"b", "d"}
        assert all(e.kind == "CALLS" for e in edges)

    def test_search_edges_by_target_names_deduplication(self):
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a", target="b", file_path="f.py", line=1)
        )
        self.store.commit()

        # Requesting "b" twice should still return only one edge
        edges = self.store.search_edges_by_target_names(["b", "b"])
        assert len(edges) == 1
        assert edges[0].target_qualified == "b"

    def test_search_edges_by_target_names_kind_filter(self):
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a", target="b", file_path="f.py", line=1)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="OTHER", source="c", target="b", file_path="f.py", line=2)
        )
        self.store.commit()

        edges = self.store.search_edges_by_target_names(["b"], kind="OTHER")
        assert len(edges) == 1
        assert edges[0].kind == "OTHER"
        assert edges[0].source_qualified == "c"

    def test_search_edges_by_target_names_as_of(self):
        SHA_OLD = "1" * 40
        SHA_NEW = "2" * 40
        now = time.time()

        # Row 1: Old version of 'b' (superseded)
        self.store._conn.execute(
            "INSERT INTO edges (kind, source_qualified, target_qualified, file_path, line, updated_at, valid_from_sha, valid_to_sha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("CALLS", "old_src", "b", "f.py", 1, now, SHA_OLD, SHA_NEW),
        )
        # Row 2: Current version of 'b'
        self.store._conn.execute(
            "INSERT INTO edges (kind, source_qualified, target_qualified, file_path, line, updated_at, valid_from_sha, valid_to_sha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("CALLS", "new_src", "b", "f.py", 1, now, SHA_NEW, None),
        )
        self.store.commit()

        # Current version (as_of="")
        edges = self.store.search_edges_by_target_names(["b"])
        assert len(edges) == 1
        assert edges[0].source_qualified == "new_src"

        # Snapshot at SHA_OLD
        edges = self.store.search_edges_by_target_names(["b"], as_of=SHA_OLD)
        assert len(edges) == 1
        assert edges[0].source_qualified == "old_src"

        # Snapshot at SHA_NEW
        edges = self.store.search_edges_by_target_names(["b"], as_of=SHA_NEW)
        assert len(edges) == 2

    def test_search_edges_by_target_names_kind_tuple(self):
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a", target="b", file_path="f.py", line=1)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="INHERITS", source="c", target="b", file_path="f.py", line=2)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="OTHER", source="d", target="b", file_path="f.py", line=3)
        )
        self.store.commit()

        edges = self.store.search_edges_by_target_names(
            ["b"], kind=("CALLS", "INHERITS")
        )
        assert len(edges) == 2
        kinds = {e.kind for e in edges}
        assert kinds == {"CALLS", "INHERITS"}

    def test_search_edges_by_target_names_kind_none(self):
        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source="a", target="b", file_path="f.py", line=1)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="OTHER", source="c", target="b", file_path="f.py", line=2)
        )
        self.store.commit()

        # kind=None should return all edges regardless of kind
        edges = self.store.search_edges_by_target_names(["b"], kind=None)
        assert len(edges) == 2
