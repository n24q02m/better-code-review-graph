import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    store = GraphStore(str(db_path))
    yield store
    store.close()


def test_get_nodes_by_qualified_names_empty(store):
    assert store.get_nodes_by_qualified_names([]) == []


def test_get_nodes_by_qualified_names_basic(store):
    node1 = NodeInfo(
        kind="Function", name="f1", file_path="a.py", line_start=1, line_end=5
    )
    node2 = NodeInfo(
        kind="Function", name="f2", file_path="a.py", line_start=6, line_end=10
    )
    store.upsert_node(node1)
    store.upsert_node(node2)
    store.commit()

    qns = ["a.py::f1", "a.py::f2", "nonexistent"]
    nodes = store.get_nodes_by_qualified_names(qns)

    assert len(nodes) == 2
    names = {n.qualified_name for n in nodes}
    assert "a.py::f1" in names
    assert "a.py::f2" in names


def test_get_nodes_by_qualified_names_duplicates(store):
    node1 = NodeInfo(
        kind="Function", name="f1", file_path="a.py", line_start=1, line_end=5
    )
    store.upsert_node(node1)
    store.commit()

    qns = ["a.py::f1", "a.py::f1", "a.py::f1"]
    nodes = store.get_nodes_by_qualified_names(qns)

    assert len(nodes) == 1
    assert nodes[0].qualified_name == "a.py::f1"


def test_get_nodes_by_qualified_names_large_batch(store):
    # Create 500 nodes to exceed batch_size=450
    expected_qns = []
    for i in range(500):
        qn = f"file.py::func_{i}"
        node = NodeInfo(
            kind="Function",
            name=f"func_{i}",
            file_path="file.py",
            line_start=i,
            line_end=i + 1,
        )
        store.upsert_node(node)
        expected_qns.append(qn)
    store.commit()

    nodes = store.get_nodes_by_qualified_names(expected_qns)
    assert len(nodes) == 500
    returned_qns = {n.qualified_name for n in nodes}
    assert len(returned_qns) == 500
    for qn in expected_qns:
        assert qn in returned_qns


def test_get_edges_by_targets_empty(store):
    assert store.get_edges_by_targets([]) == []


def test_get_edges_by_targets_basic(store):
    edge1 = EdgeInfo(kind="CALLS", source="s1", target="t1", file_path="a.py", line=1)
    edge2 = EdgeInfo(kind="CALLS", source="s2", target="t2", file_path="a.py", line=2)
    edge3 = EdgeInfo(kind="CALLS", source="s3", target="t1", file_path="b.py", line=3)
    store.upsert_edge(edge1)
    store.upsert_edge(edge2)
    store.upsert_edge(edge3)
    store.commit()

    edges = store.get_edges_by_targets(["t1", "nonexistent"])
    assert len(edges) == 2
    for e in edges:
        assert e.target_qualified == "t1"

    sources = {e.source_qualified for e in edges}
    assert sources == {"s1", "s3"}


def test_get_edges_by_targets_large_batch(store):
    # Create 500 edges to exceed batch_size=450
    target_qns = []
    for i in range(500):
        target_qn = f"target_{i}"
        edge = EdgeInfo(
            kind="CALLS", source="source", target=target_qn, file_path="f.py", line=i
        )
        store.upsert_edge(edge)
        target_qns.append(target_qn)
    store.commit()

    edges = store.get_edges_by_targets(target_qns)
    assert len(edges) == 500
    returned_targets = {e.target_qualified for e in edges}
    assert len(returned_targets) == 500


def test_get_nodes_by_files_empty(store):
    assert store.get_nodes_by_files([]) == []


def test_get_nodes_by_files_basic(store):
    node1 = NodeInfo(
        kind="Function", name="f1", file_path="a.py", line_start=1, line_end=5
    )
    node2 = NodeInfo(
        kind="Function", name="f2", file_path="b.py", line_start=1, line_end=5
    )
    node3 = NodeInfo(
        kind="Function", name="f3", file_path="a.py", line_start=6, line_end=10
    )
    store.upsert_node(node1)
    store.upsert_node(node2)
    store.upsert_node(node3)
    store.commit()

    nodes = store.get_nodes_by_files(["a.py", "b.py", "nonexistent.py"])
    assert len(nodes) == 3
    file_paths = {n.file_path for n in nodes}
    assert file_paths == {"a.py", "b.py"}

    qns = {n.qualified_name for n in nodes}
    assert qns == {"a.py::f1", "b.py::f2", "a.py::f3"}


def test_get_nodes_by_files_duplicates(store):
    node1 = NodeInfo(
        kind="Function", name="f1", file_path="a.py", line_start=1, line_end=5
    )
    store.upsert_node(node1)
    store.commit()

    nodes = store.get_nodes_by_files(["a.py", "a.py", "a.py"])
    assert len(nodes) == 1
    assert nodes[0].file_path == "a.py"


def test_get_nodes_by_files_large_batch(store):
    # Create nodes in 500 different files
    expected_files = []
    for i in range(500):
        file_path = f"file_{i}.py"
        node = NodeInfo(
            kind="Function",
            name="func",
            file_path=file_path,
            line_start=1,
            line_end=2,
        )
        store.upsert_node(node)
        expected_files.append(file_path)
    store.commit()

    nodes = store.get_nodes_by_files(expected_files)
    assert len(nodes) == 500
    returned_files = {n.file_path for n in nodes}
    assert len(returned_files) == 500
    for f in expected_files:
        assert f in returned_files
