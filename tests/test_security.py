from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo


def test_get_nodes_by_size_security(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = GraphStore(db_path)

    # Setup
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="f1",
            file_path="f1.py",
            line_start=1,
            line_end=100,
            language="python",
        )
    )
    store.commit()

    # Valid call
    nodes = store.get_nodes_by_size(min_lines=50)
    assert len(nodes) == 1

    # Malicious kind - should be treated literally and find nothing
    malicious_kind = "Function' OR 1=1--"
    nodes = store.get_nodes_by_size(min_lines=200, kind=malicious_kind)
    assert len(nodes) == 0

    # Malicious file_path_pattern
    malicious_pattern = "f1.py' OR 1=1--"
    nodes = store.get_nodes_by_size(min_lines=200, file_path_pattern=malicious_pattern)
    assert len(nodes) == 0

    store.close()


def test_search_nodes_security(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = GraphStore(db_path)

    # Setup
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="secret",
            file_path="s.py",
            line_start=1,
            line_end=10,
            language="python",
        )
    )
    store.commit()

    # Malicious kind in search
    malicious_kind = "Function' OR 1=1--"
    nodes = store.search_nodes("secret", kind=malicious_kind)
    assert len(nodes) == 0

    store.close()
