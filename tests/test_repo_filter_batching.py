"""Tests for the batched ``json_each`` repo / surviving-qn filters.

PR #488 replaced two N+1 SQL loops in ``tools.query_graph`` and
``tools.semantic_search_nodes`` with a single batched lookup via
``json_each``:

* the ``repo`` post-filter on the results / vector hits, and
* the ``valid_to_sha IS NULL`` survival filter on vector hits.

These tests verify the batched SQL produces the same rows as the
per-qn lookup it replaced — across empty inputs, missing nodes, and
many-result fanouts.
"""

from __future__ import annotations

import json

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo


@pytest.fixture
def populated_store(tmp_path):
    db_path = tmp_path / "filter.db"
    s = GraphStore(str(db_path))
    # Seed 25 nodes per repo plus 5 shared / repo-less nodes.
    for i in range(25):
        s.upsert_node(
            NodeInfo(
                kind="Function",
                name=f"a{i}",
                file_path=f"repo_a/{i}.py",
                line_start=1,
                line_end=2,
                repo_id="repo-a",
            )
        )
        s.upsert_node(
            NodeInfo(
                kind="Function",
                name=f"b{i}",
                file_path=f"repo_b/{i}.py",
                line_start=1,
                line_end=2,
                repo_id="repo-b",
            )
        )
    for i in range(5):
        s.upsert_node(
            NodeInfo(
                kind="Function",
                name=f"x{i}",
                file_path=f"shared/{i}.py",
                line_start=1,
                line_end=2,
            )
        )
    s.commit()
    yield s
    s.close()


def _batched_repo_map(store: GraphStore, qns: list[str]) -> dict[str, str]:
    """Mirror the json_each lookup used by tools.query_graph."""
    if not qns:
        return {}
    rows = store._conn.execute(
        "SELECT n.qualified_name, n.repo_id FROM nodes n "
        "JOIN json_each(?) j ON n.qualified_name = j.value",
        (json.dumps(qns),),
    ).fetchall()
    return {row["qualified_name"]: row["repo_id"] for row in rows}


def _legacy_repo_map(store: GraphStore, qns: list[str]) -> dict[str, str]:
    """The N+1 version we replaced. Used as a reference oracle."""
    out: dict[str, str] = {}
    for qn in qns:
        row = store._conn.execute(
            "SELECT repo_id FROM nodes WHERE qualified_name = ?",
            (qn,),
        ).fetchone()
        if row is not None:
            out[qn] = row["repo_id"]
    return out


def test_batched_repo_map_matches_legacy_on_empty(populated_store):
    assert _batched_repo_map(populated_store, []) == _legacy_repo_map(
        populated_store, []
    )


def test_batched_repo_map_matches_legacy_on_unknown_qn(populated_store):
    qns = ["does-not-exist", "neither-does-this"]
    assert _batched_repo_map(populated_store, qns) == _legacy_repo_map(
        populated_store, qns
    )


def test_batched_repo_map_matches_legacy_at_fanout(populated_store):
    qns = [f"repo_a/{i}.py::a{i}" for i in range(25)]
    qns += [f"repo_b/{i}.py::b{i}" for i in range(25)]
    qns += [f"shared/{i}.py::x{i}" for i in range(5)]
    # Add some misses too.
    qns += ["missing/0.py::oops"]
    assert _batched_repo_map(populated_store, qns) == _legacy_repo_map(
        populated_store, qns
    )


def test_batched_repo_map_returns_only_requested_qns(populated_store):
    """Requesting a subset must not pull in unrelated rows from the
    nodes table — the JOIN must be properly constrained."""
    qns = [f"repo_a/{i}.py::a{i}" for i in range(3)]
    out = _batched_repo_map(populated_store, qns)
    assert set(out.keys()) == set(qns)


def test_batched_repo_map_duplicate_input_is_deduplicated(populated_store):
    """If callers ask for the same qn twice, the row appears once in the
    result. ``json_each`` would emit two join rows otherwise."""
    qns = ["repo_a/0.py::a0", "repo_a/0.py::a0", "repo_a/0.py::a0"]
    out = _batched_repo_map(populated_store, qns)
    # The dict naturally dedups by key; this confirms the function
    # doesn't crash on duplicates and returns a single mapping.
    assert out == {"repo_a/0.py::a0": "repo-a"}


def _batched_surviving_qns(store: GraphStore, qns: list[str]) -> set[str]:
    """Mirror the survival check used by semantic_search_nodes."""
    if not qns:
        return set()
    rows = store._conn.execute(
        "SELECT n.qualified_name FROM nodes n "
        "JOIN json_each(?) j ON n.qualified_name = j.value "
        "WHERE n.valid_to_sha IS NULL",
        (json.dumps(qns),),
    ).fetchall()
    return {row["qualified_name"] for row in rows}


def test_batched_surviving_qns_keeps_all_when_none_invalidated(populated_store):
    """All seeded nodes have ``valid_to_sha IS NULL`` so they all survive."""
    qns = [f"repo_a/{i}.py::a{i}" for i in range(25)]
    assert _batched_surviving_qns(populated_store, qns) == set(qns)


def test_batched_surviving_qns_drops_invalidated_rows(populated_store):
    """Manually mark some rows as invalidated and confirm they drop out."""
    populated_store._conn.execute(
        "UPDATE nodes SET valid_to_sha = 'deadbeef' "
        "WHERE qualified_name = 'repo_a/0.py::a0'"
    )
    populated_store._conn.commit()

    qns = [f"repo_a/{i}.py::a{i}" for i in range(3)]
    surviving = _batched_surviving_qns(populated_store, qns)
    assert "repo_a/0.py::a0" not in surviving
    assert "repo_a/1.py::a1" in surviving
    assert "repo_a/2.py::a2" in surviving


def test_batched_surviving_qns_empty_input(populated_store):
    assert _batched_surviving_qns(populated_store, []) == set()
