import time
from unittest.mock import patch

from src.better_code_review_graph.graph import GraphStore
from src.better_code_review_graph.parser import EdgeInfo, NodeInfo
from src.better_code_review_graph.tools import query_graph


def test_callers_of_n1_performance(tmp_path):
    db_path = tmp_path / "test.db"

    with GraphStore(db_path) as store:
        # insert a target node and 500 caller nodes
        target = NodeInfo(
            kind="Function",
            name="target",
            file_path="target.py",
            line_start=1,
            line_end=10,
            language="python",
        )
        store.upsert_node(target)
        for i in range(500):
            caller = NodeInfo(
                kind="Function",
                name=f"caller{i}",
                file_path=f"caller{i}.py",
                line_start=1,
                line_end=10,
                language="python",
            )
            store.upsert_node(caller)
            edge = EdgeInfo(
                kind="CALLS",
                source=f"caller{i}.py::caller{i}",
                target="target.py::target",
                file_path=f"caller{i}.py",
                line=1,
                extra={},
            )
            store.upsert_edge(edge)

        store.commit()

    with patch("src.better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(db_path)
        mock_get_store.return_value = (store, tmp_path)

        # Test callers_of logic
        start = time.time()
        result = query_graph("callers_of", "target.py::target", repo_root=str(tmp_path))
        elapsed = time.time() - start

        assert result["status"] == "ok"
        assert len(result["results"]) == 500
        # Check that it returns fast (should take single digit ms, well under 0.2s for 500 nodes)
        assert elapsed < 0.2

        store.close()
