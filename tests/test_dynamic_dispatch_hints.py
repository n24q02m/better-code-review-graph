"""Tests for #331: dynamic_dispatch_hints in callers_of response.

When a target is referenced via patterns the AST `CALLS` edge cannot
capture (``asyncio.to_thread``, ``functools.partial``, ``map``, etc.),
``callers_of`` should still surface those references in
``dynamic_dispatch_hints`` so consumers know the AST answer is a lower
bound.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import query_graph


@pytest.fixture
def repo_with_async_dispatch(tmp_path):
    """Repo with `worker.execute_with_retry` referenced via asyncio.to_thread."""
    (tmp_path / ".git").mkdir()
    crg = tmp_path / ".code-review-graph"
    crg.mkdir()
    (crg / ".gitignore").write_text("*\n")

    worker = tmp_path / "worker.py"
    worker.write_text(
        "def execute_with_retry(fn):\n    return fn()\n",
        encoding="utf-8",
    )
    server = tmp_path / "server.py"
    server.write_text(
        "import asyncio\n"
        "from worker import execute_with_retry\n"
        "\n"
        "async def schedule():\n"
        "    await asyncio.to_thread(execute_with_retry, lambda: 1)\n"
        "    return execute_with_retry(lambda: 2)\n",
        encoding="utf-8",
    )

    db = crg / "graph.db"
    store = GraphStore(str(db))
    abs_worker = str(worker)
    abs_server = str(server)
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_worker,
            file_path=abs_worker,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="execute_with_retry",
            file_path=abs_worker,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_server,
            file_path=abs_server,
            line_start=1,
            line_end=6,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="schedule",
            file_path=abs_server,
            line_start=4,
            line_end=6,
            language="python",
        )
    )
    # Only the static call gets a CALLS edge; the asyncio.to_thread one is
    # the blind spot we want #331 to surface.
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source=f"{abs_server}::schedule",
            target=f"{abs_worker}::execute_with_retry",
            file_path=abs_server,
            line=6,
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="IMPORTS_FROM",
            source=abs_server,
            target=abs_worker,
            file_path=abs_server,
            line=2,
        )
    )
    store.commit()
    store.close()
    return tmp_path


def test_callers_of_surfaces_asyncio_to_thread_hint(repo_with_async_dispatch):
    abs_worker = str(repo_with_async_dispatch / "worker.py")
    result = query_graph(
        pattern="callers_of",
        target=f"{abs_worker}::execute_with_retry",
        repo_root=str(repo_with_async_dispatch),
    )
    assert result["status"] == "ok"
    assert "dynamic_dispatch_hints" in result
    hits = result["dynamic_dispatch_hints"]["same_file_references"]
    assert any(h["pattern"] == "asyncio.to_thread" for h in hits), hits


def test_callers_of_no_hints_when_pattern_absent(tmp_path):
    """Targets without any dispatch references -> no hints field."""
    (tmp_path / ".git").mkdir()
    crg = tmp_path / ".code-review-graph"
    crg.mkdir()
    (crg / ".gitignore").write_text("*\n")
    src = tmp_path / "plain.py"
    src.write_text("def alpha():\n    return 1\n")

    db = crg / "graph.db"
    store = GraphStore(str(db))
    abs_src = str(src)
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_src,
            file_path=abs_src,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="alpha",
            file_path=abs_src,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.commit()
    store.close()

    result = query_graph(
        pattern="callers_of",
        target=f"{abs_src}::alpha",
        repo_root=str(tmp_path),
    )
    assert result["status"] == "ok"
    assert "dynamic_dispatch_hints" not in result
