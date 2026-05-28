import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the target function. At runtime this does not require GraphStore or networkx
from better_code_review_graph.federation import backfill_commits_for_repo


def test_backfill_commits_os_error():
    """Verify backfill_commits_for_repo handles OSError from git log."""
    repo_root = Path("/tmp/fake-repo")
    store = MagicMock()
    # We need to mock (repo_root / ".git").exists()
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("subprocess.run", side_effect=OSError("Bogus OS error")),
        patch("better_code_review_graph.federation.logger") as mock_logger,
    ):
        res = backfill_commits_for_repo(store, "test-repo", repo_root)

    assert res == 0
    mock_logger.warning.assert_called_once_with(
        "Failed to git rev-list for repo %s", "test-repo"
    )


def test_backfill_commits_timeout_error():
    """Verify backfill_commits_for_repo handles TimeoutExpired from git log."""
    repo_root = Path("/tmp/fake-repo")
    store = MagicMock()
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=30),
        ),
        patch("better_code_review_graph.federation.logger") as mock_logger,
    ):
        res = backfill_commits_for_repo(store, "test-repo", repo_root)

    assert res == 0
    mock_logger.warning.assert_called_once_with(
        "Failed to git rev-list for repo %s", "test-repo"
    )


if __name__ == "__main__":
    # Manual execution for environment where pytest discovery fails
    print("Running test_backfill_commits_os_error...")
    test_backfill_commits_os_error()
    print("test_backfill_commits_os_error ok")

    print("Running test_backfill_commits_timeout_error...")
    test_backfill_commits_timeout_error()
    print("test_backfill_commits_timeout_error ok")
