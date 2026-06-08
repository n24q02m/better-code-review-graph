import pytest

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


def test_inheritors_of_enables_bare_fallback(store):
    """inheritors_of / tests_for should find relationships even when
    the edge uses an unqualified (bare) target name, even if the qualified
    target exists (e.g. has a CONTAINS edge).
    """
    # Add a node that exists (qualified name)
    store.upsert_node(
        NodeInfo(kind="Class", name="Base", file_path="a.py", line_start=1, line_end=10)
    )
    # It has a CONTAINS edge (so it is not 'truly empty' of edges)
    store.upsert_edge(
        EdgeInfo(
            kind="CONTAINS",
            source="a.py",
            target="a.py::Base",
            file_path="a.py",
            line=1,
        )
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
    _handle_inheritors_of(store, "a.py::Base", results, edges_out)

    # It SHOULD now find b.py::Sub because we enabled fallback for these tools.
    assert len(results) == 1
    assert results[0]["qualified_name"] == "b.py::Sub"
    assert len(edges_out) == 1


def test_tests_for_enables_bare_fallback(store):
    store.upsert_node(
        NodeInfo(
            kind="Function", name="target", file_path="a.py", line_start=1, line_end=10
        )
    )
    # It has a CONTAINS edge
    store.upsert_edge(
        EdgeInfo(
            kind="CONTAINS",
            source="a.py",
            target="a.py::target",
            file_path="a.py",
            line=1,
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
    node = store.get_node("a.py::target")
    _handle_tests_for(store, node, "target", "a.py::target", results)

    # It SHOULD now find the test
    assert len(results) >= 1
    assert any(r["qualified_name"] == "test_a.py::test_func" for r in results)


def test_importers_of_no_bare_fallback(store):
    # importers_of for a file
    # If we query importers of "app/a.py", it should not find someone importing bare "a.py"
    # because importers_of still uses fallback=False implicitly by not being refactored yet.

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
    _handle_importers_of(store, "app/a.py", results, edges_out)

    assert len(results) == 0


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
