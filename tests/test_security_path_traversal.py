import os
import unittest
from pathlib import Path
import tempfile
import shutil

# To allow testing locally in constrained sandbox environments,
# we mock the mcp_core modules before importing credential_state
import sys
import types
if 'mcp_core' not in sys.modules:
    mcp_core = types.ModuleType('mcp_core')
    mcp_core.storage = types.ModuleType('mcp_core.storage')
    mcp_core.storage.per_plugin_store = types.ModuleType('mcp_core.storage.per_plugin_store')
    class MockStore:
        def __init__(self, *args, **kwargs): pass
        def load(self): return {}
        def save(self, config): pass
        def clear(self): pass
    mcp_core.storage.per_plugin_store.PerPluginStore = MockStore
    sys.modules['mcp_core'] = mcp_core
    sys.modules['mcp_core.storage'] = mcp_core.storage
    sys.modules['mcp_core.storage.per_plugin_store'] = mcp_core.storage.per_plugin_store

from better_code_review_graph.credential_state import _sub_data_dir

class TestSecurityPathTraversal(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_crg_data_dir = os.environ.get("CRG_DATA_DIR")
        os.environ["CRG_DATA_DIR"] = self.temp_dir

    def tearDown(self):
        if self.original_crg_data_dir is not None:
            os.environ["CRG_DATA_DIR"] = self.original_crg_data_dir
        else:
            del os.environ["CRG_DATA_DIR"]
        shutil.rmtree(self.temp_dir)

    def test_sub_data_dir_valid(self):
        """Test that a valid sub string creates a directory properly."""
        sub = "user_123"
        path = _sub_data_dir(sub)

        # Should be inside the temp_dir / "subs"
        expected_parent = Path(self.temp_dir).resolve() / "subs"

        self.assertTrue(path.is_relative_to(expected_parent))
        self.assertEqual(path.name, "user_123")
        self.assertTrue(path.is_dir())

    def test_sub_data_dir_path_traversal(self):
        """Test that path traversal attempts are rejected."""
        # Try to break out using ../
        malicious_sub = "../../../hacked_dir"

        with self.assertRaises(ValueError) as context:
            _sub_data_dir(malicious_sub)

        self.assertIn("Invalid sub path (path traversal detected)", str(context.exception))

        # Try an absolute path
        with self.assertRaises(ValueError):
            _sub_data_dir("/etc/passwd")

if __name__ == '__main__':
    unittest.main()
