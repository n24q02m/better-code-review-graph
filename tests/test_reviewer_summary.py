"""Tests for #329: reviewer_summary in graph update response.

`graph update` should surface functions_added / functions_removed /
functions_modified / modules_newly_impacted alongside the raw edge counts
so a reviewer can scope verification subagents directly from the response.
"""

from __future__ import annotations

import subprocess

import pytest

from better_code_review_graph.tools import build_or_update_graph


def _run_git(repo: str, *args: str) -> None:
    subprocess.run(
        ["git", "-C", repo, *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def git_repo(tmp_path):
    """Real git repo with one Python file and an initial commit."""
    repo = tmp_path
    _run_git(str(repo), "init", "--initial-branch=main")
    _run_git(str(repo), "config", "user.email", "test@example.com")
    _run_git(str(repo), "config", "user.name", "test")
    src = repo / "module_a.py"
    src.write_text("def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n")
    _run_git(str(repo), "add", "module_a.py")
    _run_git(str(repo), "commit", "-m", "feat: initial")
    return repo


def test_reviewer_summary_added_removed_modified(git_repo):
    """Build, mutate the file, update -> diff matches actual additions/removals."""
    # 1. Initial build.
    build_or_update_graph(full_rebuild=True, repo_root=str(git_repo))

    # 2. Mutate: remove `alpha`, modify `beta`, add `gamma`.
    src = git_repo / "module_a.py"
    src.write_text(
        "def beta():\n    return 'changed'\n\n\ndef gamma():\n    return 3\n"
    )
    _run_git(str(git_repo), "add", "module_a.py")
    _run_git(str(git_repo), "commit", "-m", "fix: rotate functions")

    # 3. Incremental update -> reviewer_summary should reflect the diff.
    result = build_or_update_graph(
        full_rebuild=False, repo_root=str(git_repo), base="HEAD~1"
    )
    assert result["status"] == "ok"
    assert result["build_type"] == "incremental"
    summary = result["reviewer_summary"]

    added = summary["functions_added"]
    removed = summary["functions_removed"]
    modified = summary["functions_modified"]

    assert any(qn.endswith("::gamma") for qn in added), added
    assert any(qn.endswith("::alpha") for qn in removed), removed
    assert any(qn.endswith("::beta") for qn in modified), modified
    assert isinstance(summary["modules_newly_impacted"], list)


def test_reviewer_summary_no_changes_returns_empty_block(git_repo):
    """No changes -> reviewer_summary block absent (files_updated=0 path)."""
    build_or_update_graph(full_rebuild=True, repo_root=str(git_repo))
    result = build_or_update_graph(
        full_rebuild=False, repo_root=str(git_repo), base="HEAD"
    )
    # files_updated may be 0; in that case we return early WITHOUT a
    # reviewer_summary key (matches existing "no changes" shape).
    assert result["status"] == "ok"
    if result.get("files_updated", 0) == 0:
        assert "reviewer_summary" not in result or result["reviewer_summary"] == {}


def test_summary_text_includes_reviewer_counts(git_repo):
    """Human summary string includes the reviewer counts."""
    build_or_update_graph(full_rebuild=True, repo_root=str(git_repo))

    src = git_repo / "module_a.py"
    src.write_text("def gamma():\n    return 3\n")
    _run_git(str(git_repo), "add", "module_a.py")
    _run_git(str(git_repo), "commit", "-m", "feat: tweak")

    result = build_or_update_graph(
        full_rebuild=False, repo_root=str(git_repo), base="HEAD~1"
    )
    assert "Reviewer summary" in result["summary"]
