"""Tests for the SQLite-level ``kind`` filter on edge lookups.

PR #494 / #486 pushed the previously Python-side ``e.kind == "FOO"`` filtering
into the SQL ``WHERE`` clause via the new ``kind=`` parameter on
``GraphStore.get_edges_by_source`` and ``GraphStore.get_edges_by_target``.

These tests pin the contract so we can't accidentally regress the optimization
or break the (subtle) fallback semantics:

* ``kind=None`` keeps the legacy behavior (all edges).
* ``kind="CALLS"`` returns only CALLS edges.
* ``kind=("INHERITS", "IMPLEMENTS")`` returns either-kind edges in one query.
* The bare-name fallback in ``get_edges_by_target`` only fires when the
  qualified name has NO edges at all — not just no edges of the requested kind.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "kind_filter.db"
    s = GraphStore(str(db_path))
    yield s
    s.close()


def _seed(store: GraphStore) -> None:
    nodes = [
        NodeInfo(
            kind="Function", name="caller", file_path="a.py", line_start=1, line_end=5
        ),
        NodeInfo(
            kind="Function", name="callee", file_path="a.py", line_start=6, line_end=10
        ),
        NodeInfo(
            kind="Class", name="Base", file_path="a.py", line_start=11, line_end=15
        ),
        NodeInfo(kind="Class", name="Sub", file_path="b.py", line_start=1, line_end=5),
    ]
    for n in nodes:
        store.upsert_node(n)

    edges = [
        EdgeInfo(
            kind="CALLS",
            source="a.py::caller",
            target="a.py::callee",
            file_path="a.py",
            line=2,
        ),
        EdgeInfo(
            kind="CONTAINS",
            source="a.py",
            target="a.py::caller",
            file_path="a.py",
            line=1,
        ),
        EdgeInfo(
            kind="CONTAINS",
            source="a.py",
            target="a.py::callee",
            file_path="a.py",
            line=6,
        ),
        EdgeInfo(
            kind="INHERITS",
            source="b.py::Sub",
            target="a.py::Base",
            file_path="b.py",
            line=1,
        ),
        EdgeInfo(
            kind="IMPLEMENTS",
            source="b.py::Sub",
            target="a.py::Base",
            file_path="b.py",
            line=2,
        ),
    ]
    for e in edges:
        store.upsert_edge(e)
    store.commit()


def test_get_edges_by_source_kind_none_returns_all(store):
    _seed(store)
    edges = store.get_edges_by_source("a.py::caller")
    kinds = {e.kind for e in edges}
    # ``a.py::caller`` only has a single CALLS edge out; the CONTAINS edge
    # is from the parent file node.
    assert kinds == {"CALLS"}


def test_get_edges_by_source_kind_string_filter(store):
    _seed(store)
    edges = store.get_edges_by_source("a.py", kind="CONTAINS")
    assert len(edges) == 2
    assert {e.kind for e in edges} == {"CONTAINS"}


def test_get_edges_by_source_kind_no_match(store):
    _seed(store)
    edges = store.get_edges_by_source("a.py", kind="CALLS")
    assert edges == []


def test_get_edges_by_target_kind_string_filter(store):
    _seed(store)
    edges = store.get_edges_by_target("a.py::Base", kind="INHERITS")
    assert len(edges) == 1
    assert edges[0].kind == "INHERITS"


def test_get_edges_by_target_kind_tuple_filter(store):
    _seed(store)
    edges = store.get_edges_by_target("a.py::Base", kind=("INHERITS", "IMPLEMENTS"))
    assert len(edges) == 2
    assert {e.kind for e in edges} == {"INHERITS", "IMPLEMENTS"}


def test_get_edges_by_target_kind_empty_tuple_is_no_op(store):
    _seed(store)
    edges = store.get_edges_by_target("a.py::Base", kind=())
    # Empty tuple acts like no filter — same as kind=None.
    assert len(edges) == 2


def test_get_edges_by_target_fallback_only_when_truly_no_edges(store):
    """The bare-name fallback must NOT fire when the qualified name has
    edges of a different kind. Otherwise filtering by kind would silently
    swap in edges that target a *different* node that happens to share the
    bare suffix — a correctness bug for ``inheritors_of`` / ``tests_for``.
    """
    _seed(store)
    # Add a CONTAINS edge whose target is just ``Base`` (no qualifier).
    # If the fallback fired incorrectly for ``kind="INHERITS"``, we'd get
    # that CONTAINS row back as if it were an inheritance edge.
    store.upsert_edge(
        EdgeInfo(
            kind="CONTAINS",
            source="c.py",
            target="Base",
            file_path="c.py",
            line=1,
        )
    )
    store.commit()

    edges = store.get_edges_by_target("a.py::Base", kind="CALLS")
    # ``a.py::Base`` has INHERITS+IMPLEMENTS edges, so it does not look
    # "unknown" — the fallback must not fire for the CALLS filter.
    assert edges == []


def test_get_edges_by_target_fallback_fires_when_zero_edges_at_all(store):
    _seed(store)
    # Add a CALLS edge whose target is just ``Missing`` (bare name).
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source="z.py::user",
            target="Missing",
            file_path="z.py",
            line=1,
        )
    )
    store.commit()

    # Looking up a qualified name with no edges of its own should fall back
    # to bare-name matching, even with a kind filter, so that downstream
    # callers_of still resolves unqualified call sites.
    edges = store.get_edges_by_target("nowhere.py::Missing", kind="CALLS")
    assert len(edges) == 1
    assert edges[0].source_qualified == "z.py::user"


def test_get_edges_by_target_no_fallback_for_bare_lookup(store):
    """``get_edges_by_target("Bare")`` (no ``::``) never triggers the
    fallback — it would loop on itself."""
    _seed(store)
    edges = store.get_edges_by_target("Missing", kind="CALLS")
    assert edges == []
