import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Surgical mocking only during import to avoid poisoning CI environment or failing discovery
modules_to_mock = [
    "networkx",
    "tree_sitter",
    "tree_sitter_language_pack",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "mcp",
    "mcp.types",
    "mcp.server",
    "mcp.server.fastmcp",
    "fastmcp",
    "qwen3_embed",
    "cohere",
    "google.genai",
    "openai",
    "httpx",
    "pydantic_settings",
    "alembic",
    "alembic.config",
    "alembic.command",
    "alembic.script",
    "alembic.runtime",
    "alembic.runtime.migration",
]


class MockModule(MagicMock):
    def __getattr__(self, name):
        return MagicMock()


# Pre-emptively mock for the entire module session
for mod in modules_to_mock:
    if mod not in sys.modules:
        sys.modules[mod] = MockModule()

# Now import the modules
from better_code_review_graph.federation import backfill_commits_for_repo  # noqa: E402


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
