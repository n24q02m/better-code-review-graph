"""Smoke test: ``config__open_relay`` MCP tool registered after import.

Wave 3 of the Transparent Bridge v2 cascade -- registers the standard
``config__open_relay`` tool from ``mcp_core.relay.tool_helpers`` so the LLM
can re-trigger the relay form by tool call.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.server import mcp


class TestConfigOpenRelayRegistered:
    async def test_config_open_relay_in_tool_registry(self):
        """``config__open_relay`` must be registered when the server module loads."""
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "config__open_relay" in names, (
            "config__open_relay tool not registered -- "
            "register_open_relay_tool() must run at module load. "
            f"Registered tools: {sorted(names)}"
        )

    async def test_config_open_relay_alongside_canonical_tools(self):
        """The relay helper does not displace the 5 canonical tools."""
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        canonical = {"graph", "query", "review", "config", "help"}
        assert canonical.issubset(names), (
            f"Canonical 5-tool set missing entries: {canonical - names}"
        )
        assert "config__open_relay" in names

    async def test_config_open_relay_returns_expected_keys(self):
        """Tool handler must return the documented ``url/browser_opened/status`` shape.

        After spec 2026-05-01-stdio-pure-http-multiuser.md, the
        ``config__open_relay`` tool is HTTP-only -- it returns
        ``status: 'stdio_unsupported'`` when the server is running in stdio
        mode (no ``PUBLIC_URL``). The server module loads with
        ``PUBLIC_URL`` unset by default, so ``status`` is
        ``stdio_unsupported`` here.
        """
        result = await mcp.call_tool("config__open_relay", {})
        # FastMCP wraps the dict in structured/unstructured content; pull the
        # structured payload regardless of tuple/object shape.
        payload = None
        if isinstance(result, tuple) and len(result) >= 2:
            _, payload = result[0], result[1]
        else:
            payload = getattr(result, "structured_content", None) or getattr(
                result, "data", None
            )
        assert payload is not None, f"No structured payload from tool call: {result!r}"
        assert set(payload.keys()) >= {"url", "browser_opened", "status"}
        assert payload["status"] == "stdio_unsupported"
        assert payload["browser_opened"] is False
        assert payload["url"] == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
