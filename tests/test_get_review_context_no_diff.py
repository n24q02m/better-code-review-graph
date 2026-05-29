import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Isolated mocking of heavy dependencies
modules_to_mock = [
    "networkx",
    "tree_sitter",
    "tree_sitter_language_pack",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "mcp",
    "mcp.server",
    "mcp.server.fastmcp",
    "fastmcp",
    "qwen3_embed",
    "cohere",
    "google.genai",
    "openai",
    "httpx",
    "pydantic_settings",
    "n24q02m_mcp_core",
    "n24q02m_mcp_core.storage",
    "n24q02m_mcp_core.storage.per_plugin_store",
    "pygments",
    "pygments.lexers",
    "pygments.formatters",
]


class MockModule(MagicMock):
    def __getattr__(self, name):
        return MagicMock()


def setup_mocks():
    mocks = {}
    for mod in modules_to_mock:
        if mod not in sys.modules:
            mocks[mod] = MockModule()
    return mocks


# Apply mocks before importing the tool
with patch.dict(sys.modules, setup_mocks()):
    import better_code_review_graph.tools as tools_module
    from better_code_review_graph.tools import get_review_context


class TestGetReviewContextNoDiff(unittest.TestCase):
    def setUp(self):
        self.mock_store = MagicMock()
        self.mock_root = Path("/fake/repo")

        # Patch _get_store within the module where it's used
        self.get_store_patcher = patch.object(
            tools_module, "_get_store", return_value=(self.mock_store, self.mock_root)
        )
        self.mock_get_store = self.get_store_patcher.start()

    def tearDown(self):
        self.get_store_patcher.stop()

    def test_get_review_context_explicit_empty_list(self):
        """Test that passing an explicit empty list returns 'No changes detected'."""
        result = get_review_context(changed_files=[], repo_root="/fake/repo")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["summary"], "No changes detected. Nothing to review.")
        self.assertEqual(result["context"], {})
        # Store should be closed even on early return
        self.mock_store.close.assert_called_once()

    @patch.object(tools_module, "get_changed_files")
    @patch.object(tools_module, "get_staged_and_unstaged")
    def test_get_review_context_no_git_changes(self, mock_staged, mock_changed):
        """Test that if changed_files=None and git returns nothing, it returns 'No changes detected'."""
        mock_changed.return_value = []
        mock_staged.return_value = []

        result = get_review_context(changed_files=None, repo_root="/fake/repo")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["summary"], "No changes detected. Nothing to review.")
        self.mock_store.close.assert_called_once()

    @patch.object(tools_module, "_filter_valid_paths")
    def test_get_review_context_empty_impact(self, mock_filter):
        """Test the case where files are provided but impact radius is empty."""
        mock_filter.return_value = ["file1.py"]
        self.mock_store.get_impact_radius.return_value = {
            "changed_nodes": [],
            "impacted_nodes": [],
            "impacted_files": [],
            "edges": [],
            "truncated": False,
            "total_impacted": 0,
        }

        result = get_review_context(changed_files=["file1.py"], repo_root="/fake/repo")

        self.assertEqual(result["status"], "ok")
        self.assertIn("Review context for 1 changed file(s):", result["summary"])
        self.assertIn("0 directly changed nodes", result["summary"])
        self.assertIn("context", result)
        self.assertEqual(result["context"]["changed_files"], ["file1.py"])
        self.assertEqual(result["context"]["graph"]["changed_nodes"], [])
        self.mock_store.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
