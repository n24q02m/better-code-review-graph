from unittest.mock import patch

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import query_graph


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

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(db_path)
        mock_get_store.return_value = (store, tmp_path)

        # Count actual SQL statements executed while resolving children_of.
        # This is the deterministic, runner-independent signal for an N+1
        # regression: the batched implementation runs a small constant number
        # of queries regardless of result size, whereas an N+1 reimplementation
        # would issue one query per child (500+). Wall-clock timing was flaky
        # on loaded CI runners (e.g. 0.6s for the non-N+1 path), so we assert
        # on query count instead of elapsed seconds.
        query_count = 0

        def _count_queries(statement: str) -> None:
            nonlocal query_count
            query_count += 1

        store._conn.set_trace_callback(_count_queries)
        try:
            result = query_graph(
                "children_of", "parent.py::parent", repo_root=str(tmp_path)
            )
        finally:
            # query_graph may close the underlying connection; resetting the
            # trace callback then raises ProgrammingError, which we ignore.
            try:
                store._conn.set_trace_callback(None)
            except Exception:
                pass

        assert result["status"] == "ok"
        assert len(result["results"]) == 500
        # Bounded query count proves no per-child round-trip. A true N+1 would
        # scale with the 500 children; the batched path stays well under 50.
        assert query_count < 50

        # Verify result order matches the edges
        for i in range(500):
            assert result["results"][i]["name"] == f"child{i}"
