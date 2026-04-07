import tempfile
from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import query_graph


class TestQueryGraphModular:
    def setup_method(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.db_path = self.root / ".better_code_review_graph.db"
        self.store = GraphStore(str(self.db_path))
        self._seed_data()

        # Monkeypatch _get_store to return our test store
        import better_code_review_graph.tools

        self.original_get_store = better_code_review_graph.tools._get_store
        better_code_review_graph.tools._get_store = lambda root=None: (
            GraphStore(str(self.db_path)),
            self.root,
        )

    def teardown_method(self):
        import better_code_review_graph.tools

        better_code_review_graph.tools._get_store = self.original_get_store
        self.store.close()
        self.tmp_dir.cleanup()

    def _seed_data(self):
        # Files
        f1 = str(self.root / "a.py")
        f2 = str(self.root / "b.py")
        f3 = str(self.root / "test_a.py")
        Path(f1).touch()
        Path(f2).touch()
        Path(f3).touch()

        self.store.upsert_node(
            NodeInfo(
                kind="File",
                name="a.py",
                file_path=f1,
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="File",
                name="b.py",
                file_path=f2,
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="File",
                name="test_a.py",
                file_path=f3,
                line_start=1,
                line_end=10,
                language="python",
            )
        )

        # Nodes
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="func_a",
                file_path=f1,
                line_start=2,
                line_end=5,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="func_b",
                file_path=f2,
                line_start=2,
                line_end=5,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Class",
                name="Base",
                file_path=f1,
                line_start=6,
                line_end=8,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Class",
                name="Sub",
                file_path=f2,
                line_start=6,
                line_end=8,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_func_a",
                file_path=f3,
                line_start=2,
                line_end=5,
                language="python",
                is_test=True,
            )
        )

        # Edges
        qn_a = f"{f1}::func_a"
        qn_b = f"{f2}::func_b"
        qn_base = f"{f1}::Base"
        qn_sub = f"{f2}::Sub"
        qn_test = f"{f3}::test_func_a"

        self.store.upsert_edge(
            EdgeInfo(kind="CALLS", source=qn_b, target=qn_a, file_path=f2, line=3)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="IMPORTS_FROM", source=f2, target=f1, file_path=f2)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="CONTAINS", source=f1, target=qn_a, file_path=f1)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="TESTED_BY", source=qn_test, target=qn_a, file_path=f3)
        )
        self.store.upsert_edge(
            EdgeInfo(kind="INHERITS", source=qn_sub, target=qn_base, file_path=f2)
        )

        self.store.commit()

    def test_callers_of(self):
        f1 = str(self.root / "a.py")
        res = query_graph("callers_of", f"{f1}::func_a", repo_root=str(self.root))
        assert res["status"] == "ok"
        assert len(res["results"]) == 1
        assert res["results"][0]["name"] == "func_b"

    def test_callees_of(self):
        f2 = str(self.root / "b.py")
        res = query_graph("callees_of", f"{f2}::func_b", repo_root=str(self.root))
        assert res["status"] == "ok"
        assert len(res["results"]) == 1
        assert res["results"][0]["name"] == "func_a"

    def test_imports_of(self):
        f2 = str(self.root / "b.py")
        f1 = str(self.root / "a.py")
        res = query_graph("imports_of", f2, repo_root=str(self.root))
        assert res["status"] == "ok"
        assert len(res["results"]) == 1
        assert res["results"][0]["import_target"] == f1

    def test_importers_of(self):
        f1 = str(self.root / "a.py")
        res = query_graph("importers_of", f1, repo_root=str(self.root))
        assert res["status"] == "ok"
        assert len(res["results"]) == 1
        assert res["results"][0]["importer"] == str(self.root / "b.py")

    def test_children_of(self):
        f1 = str(self.root / "a.py")
        res = query_graph("children_of", f1, repo_root=str(self.root))
        assert res["status"] == "ok"
        # Should contain func_a
        names = {r["name"] for r in res["results"]}
        assert "func_a" in names

    def test_tests_for(self):
        f1 = str(self.root / "a.py")
        res = query_graph("tests_for", f"{f1}::func_a", repo_root=str(self.root))
        assert res["status"] == "ok"
        assert len(res["results"]) >= 1
        assert res["results"][0]["name"] == "test_func_a"

    def test_inheritors_of(self):
        f1 = str(self.root / "a.py")
        res = query_graph("inheritors_of", f"{f1}::Base", repo_root=str(self.root))
        assert res["status"] == "ok"
        assert len(res["results"]) == 1
        assert res["results"][0]["name"] == "Sub"

    def test_file_summary(self):
        res = query_graph("file_summary", "a.py", repo_root=str(self.root))
        assert res["status"] == "ok"
        # a.py contains a.py (file node), func_a, and Base
        assert len(res["results"]) >= 2
        names = {r["name"] for r in res["results"]}
        assert "func_a" in names
        assert "Base" in names

    def test_unknown_pattern(self):
        res = query_graph("unknown", "a.py", repo_root=str(self.root))
        assert res["status"] == "error"
        assert "Unknown pattern" in res["error"]

    def test_not_found(self):
        res = query_graph("callers_of", "nonexistent", repo_root=str(self.root))
        assert res["status"] == "not_found"

    def test_ambiguous(self):
        # We have func_a and func_b, and test_func_a.
        # If we query for "func_a", it matches func_a and test_func_a (because search_nodes is fuzzy or test_func_a contains func_a).
        # Actually search_nodes for "func_a" will match both "func_a" and "test_func_a" (likely).

        f4 = str(self.root / "d.py")
        Path(f4).touch()
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="func_a",
                file_path=f4,
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        self.store.commit()

        res = query_graph("callers_of", "func_a", repo_root=str(self.root))
        assert res["status"] == "ambiguous"
        # Matches: func_a (a.py), func_a (d.py), and potentially test_func_a (test_a.py)
        assert len(res["candidates"]) >= 2
