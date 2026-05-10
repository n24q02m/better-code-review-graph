"""Phase 3 Task 10: ``review.delta(show_line_shifts=True)``.

When a refactor moves a function (e.g. it shifts 30 lines down) the
existing diff/added/removed/modified buckets only tell the reviewer
that the symbol was modified — they do not surface the line-number
shift itself. This test module pins the new ``show_line_shifts``
opt-in flag on :func:`review_delta`.

Behaviour pinned here:

* ``show_line_shifts=False`` (default) returns just the ``diff`` payload
  produced by :func:`diff_graph` (no ``line_shifts`` key).
* ``show_line_shifts=True`` returns ``diff`` plus a ``line_shifts``
  list of ``{qualified_name, before_line, after_line}`` for every
  qualified_name that was superseded at ``to_sha`` AND whose
  ``line_start`` actually changed across the close-out + new row pair.
* Symbols superseded with the SAME ``line_start`` are excluded.
* Repo filter narrows the line_shifts list to the requested ``repo_id``.
* Multiple shifts in the same revision are all aggregated.
* Missing ``from_sha`` or ``to_sha`` returns an error (parity with
  :func:`diff_graph`).
* The MCP ``review`` tool exposes ``show_line_shifts`` via the new
  ``delta`` action.

Fixtures use :class:`TemporalIndex` to build supersede state directly
so the tests do not depend on the parser end-to-end.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.temporal import TemporalIndex
from better_code_review_graph.tools import review_delta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SHA_A = "a" * 40
_SHA_B = "b" * 40


def _make_function_node(
    name: str = "retry",
    *,
    file_path: str = "src/m.py",
    line_start: int = 10,
    line_end: int = 12,
    source_text: str = "def retry():\n    return 1\n",
    repo_id: str = "",
) -> NodeInfo:
    return NodeInfo(
        kind="Function",
        name=name,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        language="python",
        parent_name=None,
        params="()",
        return_type=None,
        modifiers=None,
        is_test=False,
        extra={},
        source_text=source_text,
        repo_id=repo_id,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    """Build a fake repo workspace with .git + .code-review-graph/graph.db."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".git").mkdir()
    crg_dir = ws / ".code-review-graph"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")
    yield ws


@pytest.fixture
def store(workspace: Path) -> Iterator[GraphStore]:
    """File-backed GraphStore inside the fake workspace."""
    db_path = workspace / ".code-review-graph" / "graph.db"
    s = GraphStore(str(db_path))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# (1) show_line_shifts=False -> no line_shifts key
# ---------------------------------------------------------------------------


def test_review_delta_returns_diff_only_when_line_shifts_disabled(
    workspace: Path, store: GraphStore
) -> None:
    """Default (show_line_shifts=False) returns diff payload without line_shifts."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(line_start=10, source_text="def retry():\n    return 1\n")
    )
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(
        _make_function_node(line_start=42, source_text="def retry():\n    return 2\n")
    )
    store.close()

    result = review_delta(repo_root=str(workspace), from_sha=_SHA_A, to_sha=_SHA_B)
    assert "diff" in result
    assert "line_shifts" not in result


# ---------------------------------------------------------------------------
# (2) show_line_shifts=True -> line_shifts populated for moved function
# ---------------------------------------------------------------------------


def test_review_delta_returns_line_shifts_when_enabled(
    workspace: Path, store: GraphStore
) -> None:
    """show_line_shifts=True returns line_shifts entry for the moved function."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(line_start=10, source_text="def retry():\n    return 1\n")
    )
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(
        _make_function_node(line_start=42, source_text="def retry():\n    return 2\n")
    )
    store.close()

    result = review_delta(
        repo_root=str(workspace),
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        show_line_shifts=True,
    )
    shifts = result["line_shifts"]
    assert len(shifts) == 1
    assert shifts[0]["qualified_name"] == "src/m.py::retry"
    assert shifts[0]["before_line"] == 10
    assert shifts[0]["after_line"] == 42


# ---------------------------------------------------------------------------
# (3) Supersede with unchanged line_start -> excluded from line_shifts
# ---------------------------------------------------------------------------


def test_review_delta_line_shifts_skips_unchanged_lines(
    workspace: Path, store: GraphStore
) -> None:
    """Supersede at to_sha but line_start unchanged -> not a line_shift."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(line_start=10, source_text="def retry():\n    return 1\n")
    )
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    # Same line_start=10 but body changes -> still a supersede, but no shift.
    idx_b.upsert_node(
        _make_function_node(line_start=10, source_text="def retry():\n    return 2\n")
    )
    store.close()

    result = review_delta(
        repo_root=str(workspace),
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        show_line_shifts=True,
    )
    assert result["line_shifts"] == []


# ---------------------------------------------------------------------------
# (4) Missing SHAs -> error
# ---------------------------------------------------------------------------


def test_review_delta_returns_error_without_shas(
    workspace: Path, store: GraphStore
) -> None:
    """review_delta requires both from_sha and to_sha."""
    store.close()
    err = review_delta(repo_root=str(workspace), from_sha="", to_sha=_SHA_B)
    assert "error" in err
    err = review_delta(repo_root=str(workspace), from_sha=_SHA_A, to_sha="")
    assert "error" in err


# ---------------------------------------------------------------------------
# (5) Repo filter narrows line_shifts to the requested repo_id
# ---------------------------------------------------------------------------


def test_review_delta_with_repo_filter(workspace: Path, store: GraphStore) -> None:
    """repo='repo_a-...' excludes line shifts from other federated repos."""
    repo_a = "repo_a-aaaaaaaa"
    repo_b = "repo_b-bbbbbbbb"

    idx_a_repo_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a_repo_a.upsert_node(
        _make_function_node(
            name="moved_a",
            file_path="a/m.py",
            line_start=10,
            source_text="def moved_a():\n    return 1\n",
            repo_id=repo_a,
        )
    )
    idx_a_repo_b = TemporalIndex(store, current_sha=_SHA_A)
    idx_a_repo_b.upsert_node(
        _make_function_node(
            name="moved_b",
            file_path="b/m.py",
            line_start=20,
            source_text="def moved_b():\n    return 1\n",
            repo_id=repo_b,
        )
    )

    idx_b_repo_a = TemporalIndex(store, current_sha=_SHA_B)
    idx_b_repo_a.upsert_node(
        _make_function_node(
            name="moved_a",
            file_path="a/m.py",
            line_start=42,
            source_text="def moved_a():\n    return 2\n",
            repo_id=repo_a,
        )
    )
    idx_b_repo_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b_repo_b.upsert_node(
        _make_function_node(
            name="moved_b",
            file_path="b/m.py",
            line_start=80,
            source_text="def moved_b():\n    return 2\n",
            repo_id=repo_b,
        )
    )
    store.close()

    only_a = review_delta(
        repo_root=str(workspace),
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        show_line_shifts=True,
        repo=repo_a,
    )
    qns_a = [s["qualified_name"] for s in only_a["line_shifts"]]
    assert "a/m.py::moved_a" in qns_a
    assert "b/m.py::moved_b" not in qns_a


# ---------------------------------------------------------------------------
# (6) Multiple shifts aggregated
# ---------------------------------------------------------------------------


def test_review_delta_aggregates_multiple_shifts(
    workspace: Path, store: GraphStore
) -> None:
    """3 functions all moved in the same commit -> all 3 in line_shifts."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    for i, name in enumerate(("alpha", "beta", "gamma")):
        idx_a.upsert_node(
            _make_function_node(
                name=name,
                file_path=f"src/{name}.py",
                line_start=10 + i,
                source_text=f"def {name}():\n    return 1\n",
            )
        )
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    for i, name in enumerate(("alpha", "beta", "gamma")):
        idx_b.upsert_node(
            _make_function_node(
                name=name,
                file_path=f"src/{name}.py",
                line_start=100 + i,
                source_text=f"def {name}():\n    return 2\n",
            )
        )
    store.close()

    result = review_delta(
        repo_root=str(workspace),
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        show_line_shifts=True,
    )
    qns = sorted(s["qualified_name"] for s in result["line_shifts"])
    assert qns == [
        "src/alpha.py::alpha",
        "src/beta.py::beta",
        "src/gamma.py::gamma",
    ]


# ---------------------------------------------------------------------------
# (7) Both diff and line_shifts present
# ---------------------------------------------------------------------------


def test_review_delta_diff_section_present_with_line_shifts(
    workspace: Path, store: GraphStore
) -> None:
    """Both diff and line_shifts keys present when show_line_shifts=True."""
    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(line_start=10, source_text="def retry():\n    return 1\n")
    )
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(
        _make_function_node(line_start=42, source_text="def retry():\n    return 2\n")
    )
    store.close()

    result = review_delta(
        repo_root=str(workspace),
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        show_line_shifts=True,
    )
    assert "diff" in result
    assert "line_shifts" in result
    # The diff payload itself is the full diff_graph response.
    assert result["diff"]["from_sha"] == _SHA_A
    assert result["diff"]["to_sha"] == _SHA_B
    modified_qns = [r["qualified_name"] for r in result["diff"]["modified"]]
    assert "src/m.py::retry" in modified_qns


# ---------------------------------------------------------------------------
# (8) MCP review tool dispatches show_line_shifts via action='delta'
# ---------------------------------------------------------------------------


def test_server_review_tool_dispatches_show_line_shifts(
    workspace: Path, store: GraphStore
) -> None:
    """The MCP `review` tool with action='delta' surfaces line_shifts."""
    from better_code_review_graph.server import review as review_tool

    idx_a = TemporalIndex(store, current_sha=_SHA_A)
    idx_a.upsert_node(
        _make_function_node(line_start=10, source_text="def retry():\n    return 1\n")
    )
    idx_b = TemporalIndex(store, current_sha=_SHA_B)
    idx_b.upsert_node(
        _make_function_node(line_start=42, source_text="def retry():\n    return 2\n")
    )
    store.close()

    raw = review_tool(
        action="delta",
        repo_root=str(workspace),
        from_sha=_SHA_A,
        to_sha=_SHA_B,
        show_line_shifts=True,
    )
    payload = json.loads(raw)
    assert "diff" in payload
    assert "line_shifts" in payload
    qns = [s["qualified_name"] for s in payload["line_shifts"]]
    assert "src/m.py::retry" in qns
