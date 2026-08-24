"""Tests for #320: renamed_in_diff query reports line-shifted symbols.

When a refactor only changes line numbers (e.g. inserts a docstring above
existing functions), the function definitions shift down without changing
behavior. ``renamed_in_diff`` should surface those shifts so a Stage 6
audit can assert "all shifts are due to expected line-count changes".
"""

from __future__ import annotations

import subprocess

import pytest

from better_code_review_graph.tools import renamed_in_diff


def _run_git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


@pytest.fixture
def shifted_repo(tmp_path):
    """Initial commit defines `formatChartTitle` at line 1; HEAD shifts it
    by inserting a 5-line preamble.
    """
    repo = tmp_path
    _run_git(str(repo), "init", "--initial-branch=main")
    _run_git(str(repo), "config", "user.email", "test@example.com")
    _run_git(str(repo), "config", "user.name", "test")

    src = repo / "module.py"
    src.write_text("def formatChartTitle():\n    return 'old'\n")
    _run_git(str(repo), "add", "module.py")
    _run_git(str(repo), "commit", "-m", "feat: initial")

    # Insert a multiline preamble that shifts the function down.
    src.write_text(
        '"""Module docstring line 1.\n'
        "Line 2.\n"
        "Line 3.\n"
        "Line 4.\n"
        '"""\n'
        "\n"
        "def formatChartTitle():\n"
        "    return 'old'\n"
    )
    _run_git(str(repo), "add", "module.py")
    _run_git(str(repo), "commit", "-m", "fix: add docstring (shifts symbol down)")
    return repo


def test_renamed_in_diff_finds_line_shift(shifted_repo):
    result = renamed_in_diff(base="HEAD~1", repo_root=str(shifted_repo))
    assert result["status"] == "ok"
    shifts = result["shifts"]
    assert any(s["symbol"] == "formatChartTitle" for s in shifts), shifts
    s = next(s for s in shifts if s["symbol"] == "formatChartTitle")
    # Symbol moved from line 1 to ~line 7.
    assert s["base_line"] == 1
    assert s["head_line"] > 1
    assert s["delta"] == s["head_line"] - s["base_line"] > 0


def test_renamed_in_diff_no_changes_returns_empty(tmp_path):
    repo = tmp_path
    _run_git(str(repo), "init", "--initial-branch=main")
    _run_git(str(repo), "config", "user.email", "test@example.com")
    _run_git(str(repo), "config", "user.name", "test")
    src = repo / "module.py"
    src.write_text("def alpha():\n    return 1\n")
    _run_git(str(repo), "add", "module.py")
    _run_git(str(repo), "commit", "-m", "feat: initial")
    _run_git(str(repo), "commit", "--allow-empty", "-m", "feat: empty")

    result = renamed_in_diff(base="HEAD~1", repo_root=str(repo))
    assert result["status"] == "ok"
    assert result["shifts"] == []


def test_renamed_in_diff_rejects_argument_injection(shifted_repo):
    with pytest.raises(ValueError, match="Invalid git ref"):
        renamed_in_diff(base="-e", repo_root=str(shifted_repo))
