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
    from better_code_review_graph.tools import (
        _LAST_CALLERS_RESULT,
        get_review_context,
        spot_check_last_callers,
    )


class TestOSErrorCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_store = MagicMock()
        self.mock_root = Path("/fake/repo")
        self.get_store_patcher = patch.object(
            tools_module, "_get_store", return_value=(self.mock_store, self.mock_root)
        )
        self.mock_get_store = self.get_store_patcher.start()
        _LAST_CALLERS_RESULT.clear()

    def tearDown(self):
        self.get_store_patcher.stop()
        _LAST_CALLERS_RESULT.clear()

    @patch("better_code_review_graph.tools.Path.read_text")
    def test_spot_check_last_callers_oserror(self, mock_read_text):
        """Test spot_check_last_callers handles OSError when reading file snippets."""
        # 1. Populate cache
        repo_path = str(self.mock_root.resolve())
        _LAST_CALLERS_RESULT[repo_path] = {
            "pattern": "callers_of",
            "target": "target_fn",
            "edges": [
                {
                    "file_path": "/fake/repo/file1.py",
                    "line": 10,
                    "source_qualified": "src_fn",
                    "target_qualified": "target_fn",
                }
            ],
        }

        # 2. Setup mock to raise OSError
        mock_read_text.side_effect = OSError("Simulated read error")

        # 3. Call spot_check_last_callers
        result = spot_check_last_callers(n=1, repo_root="/fake/repo")

        # 4. Verify results
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["samples"]), 1)
        self.assertEqual(result["samples"][0]["snippet"], "(could not read file)")

    @patch("better_code_review_graph.tools.Path.read_text")
    @patch.object(tools_module, "_filter_valid_paths")
    def test_get_review_context_oserror_in_snippets(self, mock_filter, mock_read_text):
        """Test get_review_context handles OSError in _get_source_snippets."""
        # 1. Setup mocks
        mock_filter.return_value = ["file1.py"]
        self.mock_store.get_impact_radius.return_value = {
            "changed_nodes": [MagicMock(file_path="file1.py", name="node1")],
            "impacted_nodes": [],
            "impacted_files": [],
            "edges": [],
            "truncated": False,
            "total_impacted": 0,
        }

        # Make Path.is_file return True for the fake file
        with patch("better_code_review_graph.tools.Path.is_file", return_value=True):
            # Setup mock to raise OSError
            mock_read_text.side_effect = OSError("Simulated read error")

            # 2. Call get_review_context
            result = get_review_context(
                changed_files=["file1.py"], repo_root="/fake/repo", include_source=True
            )

        # 3. Verify results
        self.assertEqual(result["status"], "ok")
        self.assertIn("source_snippets", result["context"])
        self.assertEqual(
            result["context"]["source_snippets"]["file1.py"], "(could not read file)"
        )


if __name__ == "__main__":
    unittest.main()
