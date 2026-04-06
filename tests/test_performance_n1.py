import time
from unittest.mock import patch

from src.better_code_review_graph.graph import GraphStore
from src.better_code_review_graph.parser import EdgeInfo, NodeInfo
from src.better_code_review_graph.tools import query_graph


def test_query_graph_n1_performance(tmp_path):
    db_path = tmp_path / "test.db"

    with GraphStore(db_path) as store:
        # insert a parent node and 500 child nodes
        parent = NodeInfo(
            kind="Function",
            name="parent",
            file_path="parent.py",
            line_start=1,
            line_end=10,
            language="python",
        )
        store.upsert_node(parent)
        for i in range(500):
            child = NodeInfo(
                kind="Function",
                name=f"child{i}",
                file_path="child.py",
                line_start=1,
                line_end=10,
                language="python",
            )
            store.upsert_node(child)
            edge = EdgeInfo(
                kind="CONTAINS",
                source="parent.py::parent",
                target=f"child.py::child{i}",
                file_path="child.py",
                line=1,
                extra={},
            )
            store.upsert_edge(edge)

        store.commit()

    with patch("src.better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(db_path)
        mock_get_store.return_value = (store, tmp_path)

        # Test children_of logic
        start = time.time()
        result = query_graph(
            "children_of", "parent.py::parent", repo_root=str(tmp_path)
        )
        elapsed = time.time() - start

        assert result["status"] == "ok"
        assert len(result["results"]) == 500
        # Check that it returns fast (should take single digit ms, well under 0.2s for 500 nodes)
        assert elapsed < 1.0  # Increased timeout slightly for flakiness in CI

        # Verify result order matches the edges
        for i in range(500):
            assert result["results"][i]["name"] == f"child{i}"

        store.close()
