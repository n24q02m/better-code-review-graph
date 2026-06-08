import time
from unittest.mock import patch

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import query_graph


def test_callees_of_batching_performance(tmp_path):
    db_path = tmp_path / "test.db"

    with GraphStore(db_path) as store:
        # Create a function node that will be our caller
        caller = NodeInfo(
            kind="Function",
            name="my_func",
            file_path="src/main.py",
            line_start=10,
            line_end=20,
            language="python",
        )
        store.upsert_node(caller)

        # Create 100 callee nodes
        for i in range(100):
            callee = NodeInfo(
                kind="Function",
                name=f"callee_{i}",
                file_path="src/utils.py",
                line_start=i * 10,
                line_end=i * 10 + 5,
                language="python",
            )
            store.upsert_node(callee)

            # Create an edge from the qualified name
            edge = EdgeInfo(
                kind="CALLS",
                source="src/main.py::my_func",
                target=f"src/utils.py::callee_{i}",
                file_path="src/main.py",
                line=15,
            )
            store.upsert_edge(edge)

        # Create another caller that uses bare names in edges (to test both being searched)
        caller2 = NodeInfo(
            kind="Function",
            name="bare_caller",
            file_path="src/main.py",
            line_start=30,
            line_end=40,
            language="python",
        )
        store.upsert_node(caller2)

        for i in range(100, 150):
            callee = NodeInfo(
                kind="Function",
                name=f"callee_{i}",
                file_path="src/utils.py",
                line_start=i * 10,
                line_end=i * 10 + 5,
                language="python",
            )
            store.upsert_node(callee)

            # Edge using bare name as source
            edge = EdgeInfo(
                kind="CALLS",
                source="bare_caller",
                target=f"src/utils.py::callee_{i}",
                file_path="src/main.py",
                line=35,
            )
            store.upsert_edge(edge)

        store.commit()

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:

        def mock_get_store_impl(repo_root):
            store = GraphStore(db_path)
            return store, tmp_path

        mock_get_store.side_effect = mock_get_store_impl

        # Test callees_of for qualified caller
        start = time.time()
        result = query_graph(
            "callees_of", "src/main.py::my_func", repo_root=str(tmp_path)
        )
        elapsed = time.time() - start

        assert result["status"] == "ok"
        assert len(result["results"]) == 100
        assert elapsed < 0.5

        # Test callees_of for bare caller
        start = time.time()
        result = query_graph("callees_of", "bare_caller", repo_root=str(tmp_path))
        elapsed = time.time() - start

        assert result["status"] == "ok"
        assert len(result["results"]) == 50
        assert elapsed < 0.5
