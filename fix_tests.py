content = """import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import (
    _handle_importers_of,
    _handle_inheritors_of,
    _handle_tests_for,
)


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "correctness.db"
    s = GraphStore(str(db_path))
    yield s
    s.close()


def test_inheritors_of_finds_bare_suffix(store):
    # Add a node that exists but has NO edges targeting it.
    store.upsert_node(
        NodeInfo(kind="Class", name="Base", file_path="a.py", line_start=1, line_end=10)
    )

    # Add another node that inherits from a BARE name "Base"
    store.upsert_node(
        NodeInfo(kind="Class", name="Sub", file_path="b.py", line_start=1, line_end=10)
    )
    store.upsert_edge(
        EdgeInfo(
            kind="INHERITS", source="b.py::Sub", target="Base", file_path="b.py", line=1
        )
    )

    store.commit()

    results = []
    edges_out = []
    node = store.get_node("a.py::Base")
    _handle_inheritors_of(store, node, "a.py::Base", results, edges_out)

    # It SHOULD find b.py::Sub via bare-suffix matching.
    assert len(results) == 1
    assert len(edges_out) == 1


def test_tests_for_finds_bare_suffix(store):
    store.upsert_node(
        NodeInfo(
            kind="Function", name="target", file_path="a.py", line_start=1, line_end=10
        )
    )

    # Test for bare name "target"
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="test_func",
            file_path="test_a.py",
            line_start=1,
            line_end=10,
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="TESTED_BY",
            source="test_a.py::test_func",
            target="target",
            file_path="test_a.py",
            line=1,
        )
    )

    store.commit()

    results = []
    # node argument is used for bare name lookup
    node = store.get_node("a.py::target")
    _handle_tests_for(store, node, "target", "a.py::target", results)

    assert len(results) == 1


def test_importers_of_finds_bare_suffix(store):
    # importers_of for a file
    store.upsert_node(
        NodeInfo(
            kind="File", name="a.py", file_path="app/a.py", line_start=0, line_end=0
        )
    )

    store.upsert_node(
        NodeInfo(
            kind="File", name="b.py", file_path="app/b.py", line_start=0, line_end=0
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="IMPORTS_FROM",
            source="app/b.py",
            target="a.py",
            file_path="app/b.py",
            line=1,
        )
    )

    store.commit()

    results = []
    edges_out = []
    node = store.get_node("app/a.py")
    _handle_importers_of(store, node, "app/a.py", results, edges_out)

    assert len(results) == 1


def test_get_edges_by_target_explicit_fallback(store):
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS", source="b.py::bar", target="foo", file_path="b.py", line=1
        )
    )
    store.commit()

    # With fallback=True (default)
    edges = store.get_edges_by_target("a.py::foo", kind="CALLS")
    assert len(edges) == 1

    # With fallback=False
    edges = store.get_edges_by_target("a.py::foo", kind="CALLS", fallback=False)
    assert len(edges) == 0
"""

with open("tests/test_bare_suffix_correctness.py", "w") as f:
    f.write(content)
