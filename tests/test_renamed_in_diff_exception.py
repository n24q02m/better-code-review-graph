import subprocess
from unittest.mock import patch

import pytest

from better_code_review_graph.tools import renamed_in_diff


def _run_git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


@pytest.fixture
def repo_with_file(tmp_path):
    repo = tmp_path
    _run_git(str(repo), "init", "--initial-branch=main")
    _run_git(str(repo), "config", "user.email", "test@example.com")
    _run_git(str(repo), "config", "user.name", "test")

    src = repo / "module.py"
    src.write_text("def alpha():\n    return 1\n")
    _run_git(str(repo), "add", "module.py")
    _run_git(str(repo), "commit", "-m", "feat: initial")

    src.write_text("\ndef alpha():\n    return 1\n")
    _run_git(str(repo), "add", "module.py")
    _run_git(str(repo), "commit", "-m", "feat: shift")
    return repo


def test_renamed_in_diff_parse_exception(repo_with_file):
    # Patch CodeParser in the parser module since it is imported locally in renamed_in_diff
    with patch("better_code_review_graph.parser.CodeParser") as MockParser:
        mock_instance = MockParser.return_value
        # Ensure detect_language returns something so it doesn't skip
        mock_instance.detect_language.return_value = "python"
        # Make parse_bytes throw an exception
        mock_instance.parse_bytes.side_effect = Exception("Mock parse error")

        # renamed_in_diff should catch the exception and continue (skipping the file)
        result = renamed_in_diff(base="HEAD~1", repo_root=str(repo_with_file))

        assert result["status"] == "ok"
        assert result["shifts"] == []
        assert mock_instance.parse_bytes.called
