from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


def test_json_each_injection_resistance():
    """Verify that json_each pattern is resistant to malicious input in the IN clause."""
    # Create an in-memory graph
    store = GraphStore(":memory:")

    # Add some legitimate data
    node1 = NodeInfo(
        kind="Function",
        name="normal_node",
        file_path="file.py",
        line_start=1,
        line_end=10,
    )
    store.upsert_node(node1)

    # Malicious input that would attempt to break out of a dynamic IN clause
    # or perform some other injection if concatenated.
    # Since we use json.dumps and json_each(?), this should be treated as a literal string.
    malicious_name = "'); DROP TABLE nodes; --"

    # Attempt to fetch nodes among a set containing the malicious name
    results = store.get_nodes_by_qualified_names(
        ["file.py::normal_node", malicious_name]
    )

    # Should only return the legitimate node
    assert len(results) == 1
    assert results[0].name == "normal_node"

    # Verify the table still exists
    stats = store.get_stats()
    assert stats.total_nodes == 1


def test_get_edges_among_security():
    store = GraphStore(":memory:")

    # Add node and edge
    node1 = NodeInfo(
        kind="Function", name="a", file_path="f.py", line_start=1, line_end=2
    )
    node2 = NodeInfo(
        kind="Function", name="b", file_path="f.py", line_start=3, line_end=4
    )
    store.upsert_node(node1)
    store.upsert_node(node2)

    qn1 = "f.py::a"
    qn2 = "f.py::b"
    # Source and target are qualified names
    edge = EdgeInfo(kind="CALLS", source=qn1, target=qn2, file_path="f.py", line=1)
    store.upsert_edge(edge)

    malicious_qn = "'); DELETE FROM edges; --"

    # Test get_edges_among
    edges = store.get_edges_among({qn1, malicious_qn})

    # Should not return anything as malicious_qn doesn't match and target filtering happens in Python
    # But importantly, it shouldn't have deleted the edges table content
    assert len(edges) == 0

    all_edges = store.get_all_edges()
    assert len(all_edges) == 1


def test_search_nodes_security():
    store = GraphStore(":memory:")
    # Add node
    node = NodeInfo(
        kind="Function",
        name="search_target",
        file_path="f.py",
        line_start=1,
        line_end=2,
    )
    store.upsert_node(node)

    # Malicious words
    malicious_words = ["search_target", "') OR 1=1 --"]

    # search_nodes uses json_each for words
    results = store.search_nodes(" ".join(malicious_words))

    # Should only match if BOTH match (AND logic)
    # Since "') OR 1=1 --" won't match any node name/qualified name literally, results should be empty
    assert len(results) == 0

    # Verify table still intact
    assert store.get_stats().total_nodes == 1


def test_get_nodes_by_size_security():
    store = GraphStore(":memory:")
    # Add node
    node = NodeInfo(
        kind="Function",
        name="large_function",
        file_path="f.py",
        line_start=1,
        line_end=100,
    )
    store.upsert_node(node)

    # Malicious kind
    malicious_kind = "Function' OR 1=1 --"

    # Should not return anything as 'Function\' OR 1=1 --' doesn't match literally
    results = store.get_nodes_by_size(kind=malicious_kind)
    assert len(results) == 0

    # Verify table still intact
    assert store.get_stats().total_nodes == 1
