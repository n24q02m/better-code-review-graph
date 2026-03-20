"""Shared fixtures and test helpers for better-code-review-graph tests."""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


@pytest.fixture
def tmp_graph_store(tmp_path):
    """Create a temporary GraphStore for testing."""
    db_path = tmp_path / "graph.db"
    store = GraphStore(str(db_path))
    yield store
    store.close()


def _make_node(
    name: str,
    kind: str,
    qualified_name: str,
    **kwargs,
) -> NodeInfo:
    """Helper to create a NodeInfo for testing.

    The ``qualified_name`` is only used to derive defaults for ``file_path``
    (everything before ``::``).  The actual qualified name stored in the DB is
    computed by ``GraphStore._make_qualified()`` from the NodeInfo fields.

    Common kwargs: file_path, line_start, line_end, language, parent_name,
    params, return_type, modifiers, is_test, extra.
    """
    # Derive file_path from qualified_name if not provided
    if "::" in qualified_name:
        default_file_path = qualified_name.split("::")[0]
    else:
        default_file_path = "test.py"

    return NodeInfo(
        kind=kind,
        name=name,
        file_path=kwargs.get("file_path", default_file_path),
        line_start=kwargs.get("line_start", 1),
        line_end=kwargs.get("line_end", 10),
        language=kwargs.get("language", "python"),
        parent_name=kwargs.get("parent_name"),
        params=kwargs.get("params"),
        return_type=kwargs.get("return_type"),
        modifiers=kwargs.get("modifiers"),
        is_test=kwargs.get("is_test", False),
        extra=kwargs.get("extra", {}),
    )


def _make_edge(
    kind: str,
    source: str,
    target: str,
    file_path: str,
    line: int = 1,
    **kwargs,
) -> EdgeInfo:
    """Helper to create an EdgeInfo for testing.

    ``source`` and ``target`` map to EdgeInfo.source and EdgeInfo.target
    (which are stored as source_qualified / target_qualified in the DB).
    """
    return EdgeInfo(
        kind=kind,
        source=source,
        target=target,
        file_path=file_path,
        line=line,
        extra=kwargs.get("extra", {}),
    )
