import sys
from unittest.mock import MagicMock

# Mocking dependencies BEFORE ANY OTHER IMPORT to ensure tests can run in restricted environments
mock_networkx = MagicMock()
sys.modules["networkx"] = mock_networkx
mock_tree_sitter = MagicMock()
sys.modules["tree_sitter"] = mock_tree_sitter
mock_tslp = MagicMock()
sys.modules["tree_sitter_language_pack"] = mock_tslp
mock_mcp = MagicMock()
sys.modules["mcp"] = mock_mcp
mock_fastmcp = MagicMock()
sys.modules["fastmcp"] = mock_fastmcp
mock_mcp_core = MagicMock()
sys.modules["mcp_core"] = mock_mcp_core
sys.modules["mcp_core.relay"] = MagicMock()
sys.modules["mcp_core.relay.tool_helpers"] = MagicMock()
sys.modules["mcp_core.storage"] = MagicMock()
sys.modules["mcp_core.storage.per_plugin_store"] = MagicMock()

# ALEMBIC MOCKING
mock_alembic = MagicMock()
sys.modules["alembic"] = mock_alembic
sys.modules["alembic.config"] = MagicMock()
sys.modules["alembic.command"] = MagicMock()
sys.modules["alembic.script"] = MagicMock()
sys.modules["alembic.runtime"] = MagicMock()
sys.modules["alembic.runtime.migration"] = MagicMock()

import subprocess
from pathlib import Path
from unittest.mock import patch

# Now import the modules
from better_code_review_graph.federation import backfill_commits_for_repo


def test_backfill_commits_os_error(caplog):
    """Verify backfill_commits_for_repo handles OSError from git log."""
    repo_root = Path("/tmp/fake-repo")
    store = MagicMock()
    # We need to mock (repo_root / ".git").exists()
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("subprocess.run", side_effect=OSError("Bogus OS error")),
    ):
        res = backfill_commits_for_repo(store, "test-repo", repo_root)

    assert res == 0
    assert "Failed to git rev-list for repo test-repo" in caplog.text


def test_backfill_commits_timeout_error(caplog):
    """Verify backfill_commits_for_repo handles TimeoutExpired from git log."""
    repo_root = Path("/tmp/fake-repo")
    store = MagicMock()
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=30),
        ),
    ):
        res = backfill_commits_for_repo(store, "test-repo", repo_root)

    assert res == 0
    assert "Failed to git rev-list for repo test-repo" in caplog.text


if __name__ == "__main__":
    # Manual execution logic for environments where pytest conftest fails due to missing deps
    import logging

    logging.basicConfig(level=logging.INFO)

    class CapLog:
        def __init__(self):
            self.text = ""

        def append(self, text):
            self.text += text

    caplog = CapLog()

    # Mock logging to capture it
    with patch("better_code_review_graph.federation.logger") as mock_logger:

        def side_effect(msg, *args):
            caplog.append(msg % args)

        mock_logger.warning.side_effect = side_effect

        print("Running test_backfill_commits_os_error...")
        test_backfill_commits_os_error(caplog)
        print("test_backfill_commits_os_error ok")

        caplog.text = ""
        print("Running test_backfill_commits_timeout_error...")
        test_backfill_commits_timeout_error(caplog)
        print("test_backfill_commits_timeout_error ok")
