"""Tests for MCP tool functions."""

import tempfile
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


class TestTools:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)
        self._seed_data()

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def _seed_data(self):
        """Seed the store with test data."""
        # File nodes
        self.store.upsert_node(
            NodeInfo(
                kind="File",
                name="/repo/auth.py",
                file_path="/repo/auth.py",
                line_start=1,
                line_end=50,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="File",
                name="/repo/main.py",
                file_path="/repo/main.py",
                line_start=1,
                line_end=30,
                language="python",
            )
        )
        # Class
        self.store.upsert_node(
            NodeInfo(
                kind="Class",
                name="AuthService",
                file_path="/repo/auth.py",
                line_start=5,
                line_end=40,
                language="python",
            )
        )
        # Functions
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="login",
                file_path="/repo/auth.py",
                line_start=10,
                line_end=20,
                language="python",
                parent_name="AuthService",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="process",
                file_path="/repo/main.py",
                line_start=5,
                line_end=15,
                language="python",
            )
        )
        # Test
        self.store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_login",
                file_path="/repo/test_auth.py",
                line_start=1,
                line_end=10,
                language="python",
                is_test=True,
            )
        )

        # Edges
        self.store.upsert_edge(
            EdgeInfo(
                kind="CONTAINS",
                source="/repo/auth.py",
                target="/repo/auth.py::AuthService",
                file_path="/repo/auth.py",
            )
        )
        self.store.upsert_edge(
            EdgeInfo(
                kind="CONTAINS",
                source="/repo/auth.py::AuthService",
                target="/repo/auth.py::AuthService.login",
                file_path="/repo/auth.py",
            )
        )
        self.store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/repo/main.py::process",
                target="/repo/auth.py::AuthService.login",
                file_path="/repo/main.py",
                line=10,
            )
        )
        self.store.commit()

    def test_search_nodes(self):
        # Direct call to store (tools need repo_root, which is harder to mock)
        results = self.store.search_nodes("login")
        names = {r.name for r in results}
        assert "login" in names

    def test_search_nodes_by_kind(self):
        results = self.store.search_nodes("auth")
        # Should find both AuthService class and auth.py file
        assert len(results) >= 1

    def test_stats(self):
        stats = self.store.get_stats()
        assert stats.total_nodes == 6
        assert stats.total_edges == 3
        assert stats.files_count == 2
        assert "python" in stats.languages

    def test_impact_from_auth(self):
        result = self.store.get_impact_radius(["/repo/auth.py"], max_depth=2)
        # Changing auth.py should impact main.py (which calls login)
        impacted_qns = {n.qualified_name for n in result["impacted_nodes"]}
        # process() in main.py calls login(), so it should be impacted
        assert (
            "/repo/main.py::process" in impacted_qns or "/repo/main.py" in impacted_qns
        )
        # Should include truncation metadata
        assert result["truncated"] is False
        assert result["total_impacted"] >= 1

    def test_impact_radius_not_truncated(self):
        """Impact radius with high max_nodes returns truncated=False."""
        result = self.store.get_impact_radius(
            ["/repo/auth.py"], max_depth=2, max_nodes=500
        )
        assert result["truncated"] is False
        assert result["total_impacted"] == len(result["impacted_nodes"])

    def test_impact_radius_truncated(self):
        """Impact radius with very small max_nodes triggers truncation."""
        # Build a dense graph: a chain of functions calling each other
        # file_a::f0 -> file_b::f1 -> file_c::f2 -> ... -> file_n::fn
        num_nodes = 20
        for i in range(num_nodes):
            fpath = f"/repo/chain_{i}.py"
            self.store.upsert_node(
                NodeInfo(
                    kind="File",
                    name=fpath,
                    file_path=fpath,
                    line_start=1,
                    line_end=10,
                    language="python",
                )
            )
            self.store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=f"func_{i}",
                    file_path=fpath,
                    line_start=1,
                    line_end=10,
                    language="python",
                )
            )
        # Create a chain of CALLS edges
        for i in range(num_nodes - 1):
            self.store.upsert_edge(
                EdgeInfo(
                    kind="CALLS",
                    source=f"/repo/chain_{i}.py::func_{i}",
                    target=f"/repo/chain_{i + 1}.py::func_{i + 1}",
                    file_path=f"/repo/chain_{i}.py",
                    line=5,
                )
            )
        self.store.commit()

        # Use max_nodes=3 so BFS hits the cap quickly
        result = self.store.get_impact_radius(
            ["/repo/chain_0.py"], max_depth=10, max_nodes=3
        )
        assert result["truncated"] is True
        assert result["total_impacted"] >= 1

    def test_query_children_of(self):
        edges = self.store.get_edges_by_source("/repo/auth.py")
        contains = [e for e in edges if e.kind == "CONTAINS"]
        assert len(contains) >= 1

    def test_query_callers(self):
        edges = self.store.get_edges_by_target("/repo/auth.py::AuthService.login")
        callers = [e for e in edges if e.kind == "CALLS"]
        assert len(callers) == 1
        assert callers[0].source_qualified == "/repo/main.py::process"
