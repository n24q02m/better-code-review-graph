import sys
from unittest.mock import MagicMock

# Mock required dependencies
sys.modules['tree_sitter_language_pack'] = MagicMock()
sys.modules['tree_sitter'] = MagicMock()
sys.modules['mcp_core'] = MagicMock()
sys.modules['mcp_core.relay'] = MagicMock()
sys.modules['mcp_core.relay.tool_helpers'] = MagicMock()
sys.modules['fastmcp'] = MagicMock()
sys.modules['alembic'] = MagicMock()
sys.modules['alembic.config'] = MagicMock()
sys.modules['watchdog'] = MagicMock()
sys.modules['watchdog.events'] = MagicMock()
sys.modules['watchdog.observers'] = MagicMock()
sys.modules['loguru'] = MagicMock()
sys.modules['qwen3_embed'] = MagicMock()
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.types'] = MagicMock()
sys.modules['mcp.server'] = MagicMock()
sys.modules['mcp.server.fastmcp'] = MagicMock()

import pytest
if __name__ == "__main__":
    sys.exit(pytest.main(["-v", "tests/test_tools.py"]))
