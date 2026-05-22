import sys
from unittest.mock import MagicMock

class MockMcpCore(MagicMock):
    def __getattr__(self, name):
        return MagicMock()

sys.modules['mcp_core'] = MockMcpCore()
sys.modules['mcp_core.relay'] = MockMcpCore()
sys.modules['mcp_core.relay.tool_helpers'] = MockMcpCore()
sys.modules['mcp_core.storage'] = MockMcpCore()
sys.modules['mcp_core.storage.per_plugin_store'] = MockMcpCore()
sys.modules['fastmcp'] = MockMcpCore()
sys.modules['mcp'] = MockMcpCore()
sys.modules['mcp.types'] = MockMcpCore()
sys.modules['mcp.server'] = MockMcpCore()

import pytest
sys.exit(pytest.main(["-v", "tests/test_graph_batch_fetch.py"]))
