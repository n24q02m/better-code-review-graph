"""Tests for the graph storage and query engine."""

import tempfile
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from tests.conftest import _make_node


class TestGraphStore:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def _make_file_node(self, path="/test/file.py"):
        return NodeInfo(
            kind="File",
            name=path,
            file_path=path,
            line_start=1,
            line_end=100,
            language="python",
        )

    def _make_func_node(
        self, name="my_func", path="/test/file.py", parent=None, is_test=False
    ):
        return NodeInfo(
            kind="Test" if is_test else "Function",
            name=name,
            file_path=path,
            line_start=10,
            line_end=20,
            language="python",
            parent_name=parent,
            is_test=is_test,
        )

    def _make_class_node(self, name="MyClass", path="/test/file.py"):
        return NodeInfo(
            kind="Class",
            name=name,
            file_path=path,
            line_start=5,
            line_end=50,
            language="python",
        )

    def test_upsert_and_get_node(self):
        node = self._make_file_node()
        self.store.upsert_node(node)
        self.store.commit()

        result = self.store.get_node("/test/file.py")
        assert result is not None
        assert result.kind == "File"
        assert result.name == "/test/file.py"

    def test_upsert_function_node(self):
        func = self._make_func_node()
        self.store.upsert_node(func)
        self.store.commit()

        result = self.store.get_node("/test/file.py::my_func")
        assert result is not None
        assert result.kind == "Function"
        assert result.name == "my_func"

    def test_upsert_method_node(self):
        method = self._make_func_node(name="do_thing", parent="MyClass")
        self.store.upsert_node(method)
        self.store.commit()

        result = self.store.get_node("/test/file.py::MyClass.do_thing")
        assert result is not None
        assert result.parent_name == "MyClass"

    def test_upsert_edge(self):
        edge = EdgeInfo(
            kind="CALLS",
            source="/test/file.py::func_a",
            target="/test/file.py::func_b",
            file_path="/test/file.py",
            line=15,
        )
        self.store.upsert_edge(edge)
        self.store.commit()

        edges = self.store.get_edges_by_source("/test/file.py::func_a")
        assert len(edges) == 1
        assert edges[0].kind == "CALLS"
        assert edges[0].target_qualified == "/test/file.py::func_b"

    def test_remove_file_data(self):
        node = self._make_file_node()
        func = self._make_func_node()
        self.store.upsert_node(node)
        self.store.upsert_node(func)
        self.store.commit()

        self.store.remove_file_data("/test/file.py")
        self.store.commit()

        assert self.store.get_node("/test/file.py") is None
        assert self.store.get_node("/test/file.py::my_func") is None

    def test_store_file_nodes_edges(self):
        nodes = [self._make_file_node(), self._make_func_node()]
        edges = [
            EdgeInfo(
                kind="CONTAINS",
                source="/test/file.py",
                target="/test/file.py::my_func",
                file_path="/test/file.py",
            )
        ]
        self.store.store_file_nodes_edges("/test/file.py", nodes, edges)

        result = self.store.get_nodes_by_file("/test/file.py")
        assert len(result) == 2

    def test_search_nodes(self):
        self.store.upsert_node(self._make_func_node("authenticate"))
        self.store.upsert_node(self._make_func_node("authorize"))
        self.store.upsert_node(self._make_func_node("process"))
        self.store.commit()

        results = self.store.search_nodes("auth")
        names = {r.name for r in results}
        assert "authenticate" in names
        assert "authorize" in names
        assert "process" not in names

    def test_get_stats(self):
        self.store.upsert_node(self._make_file_node())
        self.store.upsert_node(self._make_func_node())
        self.store.upsert_node(self._make_class_node())
        self.store.upsert_edge(
            EdgeInfo(
                kind="CONTAINS",
                source="/test/file.py",
                target="/test/file.py::my_func",
                file_path="/test/file.py",
            )
        )
        self.store.commit()

        stats = self.store.get_stats()
        assert stats.total_nodes == 3
        assert stats.total_edges == 1
        assert stats.nodes_by_kind["File"] == 1
        assert stats.nodes_by_kind["Function"] == 1
        assert stats.nodes_by_kind["Class"] == 1
        assert "python" in stats.languages

    def test_impact_radius(self):
        # Create a chain: file_a -> func_a -> (calls) -> func_b in file_b
        self.store.upsert_node(self._make_file_node("/a.py"))
        self.store.upsert_node(self._make_func_node("func_a", "/a.py"))
        self.store.upsert_node(self._make_file_node("/b.py"))
        self.store.upsert_node(self._make_func_node("func_b", "/b.py"))
        self.store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::func_a",
                target="/b.py::func_b",
                file_path="/a.py",
                line=10,
            )
        )
        self.store.commit()

        result = self.store.get_impact_radius(["/a.py"], max_depth=2)
        assert len(result["changed_nodes"]) > 0
        # func_b in /b.py should be impacted
        impacted_qns = {n.qualified_name for n in result["impacted_nodes"]}
        assert "/b.py::func_b" in impacted_qns or "/b.py" in impacted_qns

    def test_upsert_edge_preserves_multiple_call_sites(self):
        """Multiple CALLS edges to the same target from the same source on different lines."""
        edge1 = EdgeInfo(
            kind="CALLS",
            source="/test/file.py::caller",
            target="/test/file.py::helper",
            file_path="/test/file.py",
            line=10,
        )
        edge2 = EdgeInfo(
            kind="CALLS",
            source="/test/file.py::caller",
            target="/test/file.py::helper",
            file_path="/test/file.py",
            line=20,
        )
        self.store.upsert_edge(edge1)
        self.store.upsert_edge(edge2)
        self.store.commit()

        edges = self.store.get_edges_by_source("/test/file.py::caller")
        assert len(edges) == 2
        lines = {e.line for e in edges}
        assert lines == {10, 20}

    def test_metadata(self):
        self.store.set_metadata("test_key", "test_value")
        assert self.store.get_metadata("test_key") == "test_value"
        assert self.store.get_metadata("nonexistent") is None


# --- Multi-word search tests (Task 2.1) ---


def test_search_nodes_multi_word(tmp_graph_store):
    """Multi-word queries should match nodes containing ALL words (AND logic)."""
    store = tmp_graph_store
    store.upsert_node(
        _make_node(
            "verify_firebase_token", "Function", "auth.py::verify_firebase_token"
        )
    )
    store.upsert_node(_make_node("FirebaseAuth", "Class", "auth.py::FirebaseAuth"))
    store.upsert_node(_make_node("get_user", "Function", "user.py::get_user"))
    store.commit()

    results = store.search_nodes("firebase auth", limit=10)
    names = [r.name for r in results]
    # Both words must appear: "firebase" AND "auth"
    assert "verify_firebase_token" in names
    assert "FirebaseAuth" in names
    assert "get_user" not in names


def test_search_nodes_multi_word_partial(tmp_graph_store):
    """Each word must match -- nodes matching only one word are excluded."""
    store = tmp_graph_store
    store.upsert_node(
        _make_node("RAGWorkflowState", "Class", "rag.py::RAGWorkflowState")
    )
    store.upsert_node(
        _make_node("process_pipeline", "Function", "pipe.py::process_pipeline")
    )
    store.commit()

    results = store.search_nodes("RAG pipeline", limit=10)
    # RAGWorkflowState matches "RAG" but not "pipeline" -> excluded
    # process_pipeline matches "pipeline" but not "RAG" -> excluded
    assert len(results) == 0

    # Single word should match
    results_single = store.search_nodes("RAG", limit=10)
    assert len(results_single) == 1
    assert results_single[0].name == "RAGWorkflowState"
