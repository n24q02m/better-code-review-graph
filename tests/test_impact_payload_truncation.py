"""Tests for #315: impact payload-size auto-truncation.

When an `impact` response would exceed the configured size cap (default
500KB), the impacted_nodes + edges arrays are trimmed and the response
includes ``results_truncated=True`` + a reason and hint.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import get_impact_radius


@pytest.fixture
def dense_graph(tmp_path):
    """Repo with a dense impact graph: 200 functions all callers of one root."""
    (tmp_path / ".git").mkdir()
    crg = tmp_path / ".code-review-graph"
    crg.mkdir()
    (crg / ".gitignore").write_text("*\n")
    db = crg / "graph.db"
    store = GraphStore(str(db))

    abs_root = str(tmp_path / "root.py")
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_root,
            file_path=abs_root,
            line_start=1,
            line_end=10,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="root_fn",
            file_path=abs_root,
            line_start=2,
            line_end=4,
            language="python",
        )
    )

    # 200 callers, each in its own file with verbose qualified names so the
    # serialized payload is ~tens of KB.
    for i in range(200):
        fp = str(tmp_path / f"caller_{i}.py")
        store.upsert_node(
            NodeInfo(
                kind="File",
                name=fp,
                file_path=fp,
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name=f"long_named_caller_function_{i:04d}_with_padding",
                file_path=fp,
                line_start=2,
                line_end=4,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source=f"{fp}::long_named_caller_function_{i:04d}_with_padding",
                target=f"{abs_root}::root_fn",
                file_path=fp,
                line=3,
            )
        )
    store.commit()
    store.close()
    return tmp_path


def test_impact_truncates_when_payload_exceeds_cap(dense_graph):
    """Tiny payload cap -> response is auto-truncated."""
    result = get_impact_radius(
        changed_files=["root.py"],
        max_depth=2,
        max_results=10_000,
        max_payload_bytes=2_000,  # very small to force truncation
        repo_root=str(dense_graph),
    )
    assert result["status"] == "ok"
    assert result.get("results_truncated") is True
    assert "reason" in result
    assert "hint" in result
    assert "max_depth=1" in result["hint"]
    assert result["original_impacted_count"] >= len(result["impacted_nodes"])


def test_impact_no_truncation_when_under_cap(dense_graph):
    """Generous cap -> no truncation flag."""
    result = get_impact_radius(
        changed_files=["root.py"],
        max_depth=2,
        max_results=10_000,
        max_payload_bytes=10_000_000,  # 10MB; nothing gets trimmed
        repo_root=str(dense_graph),
    )
    assert result["status"] == "ok"
    assert "results_truncated" not in result


def test_impact_disabled_when_cap_is_zero(dense_graph):
    """``max_payload_bytes=0`` opts out of size-based truncation."""
    result = get_impact_radius(
        changed_files=["root.py"],
        max_depth=2,
        max_results=10_000,
        max_payload_bytes=0,
        repo_root=str(dense_graph),
    )
    assert result["status"] == "ok"
    assert "results_truncated" not in result
