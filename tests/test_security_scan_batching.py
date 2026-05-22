"""Tests for batched persistence in security_scan.

PR #492 replaced a per-row ``UPDATE`` loop in ``_persist_security_tags``
with a single ``executemany``. PR #493/#491/#484 swapped ``fetchall()``
for direct cursor iteration in ``security_scan`` so we don't pin every
node's ``source_text`` in memory at once.

These tests pin the behavior of both code paths.
"""

from __future__ import annotations

import json

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.security.heuristic import Tag
from better_code_review_graph.tools import _persist_security_tags, security_scan


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "sec_scan.db"
    s = GraphStore(str(db_path))
    yield s
    s.close()


def test_persist_security_tags_skips_repo_wide(store):
    """Only node-anchored tags are written; ``(repo-wide)`` is dropped."""
    tags_by_node = {
        "(repo-wide)": [Tag("X", "HIGH", "x", 1)],
        "a.py::f": [Tag("Y", "LOW", "y", 2)],
    }
    # Need the node to actually exist so the UPDATE has a row to hit.
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="f",
            file_path="a.py",
            line_start=1,
            line_end=2,
        )
    )
    store.commit()
    _persist_security_tags(store, tags_by_node)
    row = store._conn.execute(
        "SELECT security_tags FROM nodes WHERE qualified_name = ?",
        ("a.py::f",),
    ).fetchone()
    assert json.loads(row["security_tags"]) == ["Y:LOW"]


def test_persist_security_tags_empty_dict_is_noop(store):
    """No tags -> no executemany call, no commit needed."""
    # Should not raise even though the store has nothing in it.
    _persist_security_tags(store, {})


def test_persist_security_tags_only_repo_wide_is_noop(store):
    """All tags being repo-wide -> still no UPDATEs (no rows to anchor to)."""
    _persist_security_tags(
        store,
        {"(repo-wide)": [Tag("X", "HIGH", "x", 1)]},
    )
    # No commit attempted, but the store should still be readable.
    rows = store._conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()
    assert rows["n"] == 0


def test_persist_security_tags_writes_all_rows(store):
    """Multiple tagged nodes all get persisted (we don't truncate or skip
    rows when batching). Verifies behavioral correctness — the underlying
    ``executemany`` is a perf optimization, not a contract change.
    """
    for i in range(5):
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name=f"f{i}",
                file_path="a.py",
                line_start=i,
                line_end=i + 1,
            )
        )
    store.commit()
    tags_by_node = {f"a.py::f{i}": [Tag(f"R{i}", "MEDIUM", "m", i)] for i in range(5)}
    _persist_security_tags(store, tags_by_node)

    for i in range(5):
        row = store._conn.execute(
            "SELECT security_tags FROM nodes WHERE qualified_name = ?",
            (f"a.py::f{i}",),
        ).fetchone()
        assert json.loads(row["security_tags"]) == [f"R{i}:MEDIUM"]


def test_persist_security_tags_multi_tag_per_node(store):
    """Multiple tags on one node serialize in deterministic order."""
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="f",
            file_path="a.py",
            line_start=1,
            line_end=2,
        )
    )
    store.commit()
    tags = [
        Tag("A", "LOW", "a", 1),
        Tag("B", "HIGH", "b", 2),
        Tag("C", "CRITICAL", "c", 3),
    ]
    _persist_security_tags(store, {"a.py::f": tags})
    row = store._conn.execute(
        "SELECT security_tags FROM nodes WHERE qualified_name = ?",
        ("a.py::f",),
    ).fetchone()
    assert json.loads(row["security_tags"]) == ["A:LOW", "B:HIGH", "C:CRITICAL"]


def test_security_scan_payload_shape(tmp_path):
    """End-to-end smoke: ``security_scan`` returns the expected payload
    shape and doesn't crash even though the cursor-iteration codepath
    can no longer use ``len(rows)`` accounting."""
    # `_validate_repo_root` requires either a ``.git`` ancestor or
    # a ``.code-review-graph`` directory before it will accept ``repo_root``.
    crg_dir = tmp_path / ".code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))
    try:
        for i in range(3):
            store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=f"f{i}",
                    file_path="a.py",
                    line_start=i,
                    line_end=i + 1,
                    extra={"source_text": f"def f{i}(): pass"},
                )
            )
        store.commit()
    finally:
        store.close()

    payload = security_scan(repo_root=str(tmp_path), engine="heuristic")
    assert payload["engine"] == "heuristic"
    assert "total" in payload
    assert "by_severity" in payload
    assert isinstance(payload["tags_by_node"], dict)
