"""Phase 5: Live MCP protocol test for better-code-review-graph.

Spawns the MCP server as a subprocess and communicates via the MCP protocol
(JSON-RPC over stdio), testing ALL tools through the actual transport layer.

Tests the 3-tier tool architecture: graph (mega-tool) + config + help.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

SAMPLE_PYTHON = '''\
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b


def calculate(op: str, a: int, b: int) -> int:
    """Dispatch to add or multiply based on op string."""
    if op == "add":
        return add(a, b)
    return multiply(a, b)


class Calculator:
    """Simple calculator with history."""

    def __init__(self):
        self.history: list[int] = []

    def run(self, op: str, a: int, b: int) -> int:
        result = calculate(op, a, b)
        self.history.append(result)
        return result
'''

SAMPLE_TEST = """\
from calculator import add, multiply


def test_add():
    assert add(1, 2) == 3


def test_multiply():
    assert multiply(3, 4) == 12
"""

SAMPLE_GO = """\
package main

import "fmt"

func greet(name string) string {
    return fmt.Sprintf("Hello, %s!", name)
}

func main() {
    fmt.Println(greet("world"))
}
"""


@pytest.fixture()
def sample_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with sample Python and Go files."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # Init git repo
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    # Write sample files
    (repo / "calculator.py").write_text(SAMPLE_PYTHON)
    (repo / "test_calculator.py").write_text(SAMPLE_TEST)
    (repo / "main.go").write_text(SAMPLE_GO)

    # Commit so git diff works
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    return repo


def _parse_result_text(result) -> dict | str:
    """Extract text from MCP call_tool result and try to parse as JSON."""
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


@pytest.mark.integration
class TestLiveMCP:
    """Live MCP protocol tests -- spawns server subprocess."""

    @staticmethod
    def _server_params() -> StdioServerParameters:
        return StdioServerParameters(
            command="uv",
            args=["run", "better-code-review-graph", "serve"],
            env={**os.environ, "EMBEDDING_BACKEND": "local"},
        )

    # ------------------------------------------------------------------
    # 1. Tool listing — exactly 3 tools
    # ------------------------------------------------------------------
    async def test_list_tools(self):
        """Server exposes exactly 3 tools: graph, config, help."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                expected = {"graph", "config", "help"}
                assert expected == names, f"Expected {expected}, got {names}"

    # ------------------------------------------------------------------
    # 2. Graph tool — happy path
    # ------------------------------------------------------------------
    async def test_graph_build(self, sample_repo: Path):
        """graph action=build with full_rebuild parses files."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("status") == "ok"
                assert data.get("files_parsed", 0) > 0

    async def test_graph_stats(self, sample_repo: Path):
        """graph action=stats returns node counts after build."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {"action": "stats", "repo_root": str(sample_repo)},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("total_nodes", 0) > 0

    async def test_graph_search(self, sample_repo: Path):
        """graph action=search returns results for a known symbol."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {
                        "action": "search",
                        "query": "calculator",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                results = data.get("results", [])
                assert len(results) > 0, "Expected at least one search result"

    async def test_graph_query_file_summary(self, sample_repo: Path):
        """graph action=query with file_summary pattern returns nodes."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {
                        "action": "query",
                        "pattern": "file_summary",
                        "target": "calculator.py",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                results = data.get("results", [])
                assert len(results) > 0

    async def test_graph_impact(self, sample_repo: Path):
        """graph action=impact returns impact data for changed files."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {
                        "action": "impact",
                        "changed_files": ["calculator.py"],
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("status") == "ok"

    async def test_graph_review(self, sample_repo: Path):
        """graph action=review produces review context."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {
                        "action": "review",
                        "changed_files": ["calculator.py"],
                        "repo_root": str(sample_repo),
                        "include_source": False,
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert len(data) > 0

    async def test_graph_embed(self, sample_repo: Path):
        """graph action=embed computes embeddings for graph nodes."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {"action": "embed", "repo_root": str(sample_repo)},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("newly_embedded", 0) > 0

    async def test_graph_large_functions(self, sample_repo: Path):
        """graph action=large_functions works with low threshold."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {
                        "action": "large_functions",
                        "min_lines": 3,
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                results = data.get("results", [])
                assert len(results) > 0

    # ------------------------------------------------------------------
    # 3. Config tool — happy path
    # ------------------------------------------------------------------
    async def test_config_status(self):
        """config action=status returns server info."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "config", {"action": "status"}
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("status") == "ok"
                assert "version" in data

    async def test_config_set_log_level(self):
        """config action=set updates log level."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "config",
                    {"action": "set", "key": "log_level", "value": "DEBUG"},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("status") == "updated"

    # ------------------------------------------------------------------
    # 4. Help tool
    # ------------------------------------------------------------------
    async def test_help_graph(self):
        """help topic=graph returns documentation content."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("help", {"topic": "graph"})
                data = _parse_result_text(result)
                # Help returns markdown text (not JSON), or fallback JSON
                if isinstance(data, str):
                    assert len(data) > 50, "Expected non-empty docs content"
                else:
                    # Fallback loaded from LLM-OPTIMIZED-REFERENCE.md
                    content = data.get("content", "")
                    assert len(content) > 0 or "error" not in data

    async def test_help_config(self):
        """help topic=config returns config documentation."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("help", {"topic": "config"})
                data = _parse_result_text(result)
                if isinstance(data, str):
                    assert len(data) > 50
                else:
                    content = data.get("content", "")
                    assert len(content) > 0 or "error" not in data

    # ------------------------------------------------------------------
    # 5. Error paths
    # ------------------------------------------------------------------
    async def test_graph_unknown_action(self):
        """graph with unknown action returns error."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "graph", {"action": "nonexistent_action"}
                )
                data = _parse_result_text(result)
                if isinstance(data, dict):
                    assert "error" in data
                    assert "valid_actions" in data

    async def test_graph_query_invalid_pattern(self, sample_repo: Path):
        """graph action=query with invalid pattern returns error."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": str(sample_repo),
                    },
                )
                result = await session.call_tool(
                    "graph",
                    {
                        "action": "query",
                        "pattern": "nonexistent_pattern",
                        "target": "calculator.py",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                if isinstance(data, dict):
                    text = json.dumps(data).lower()
                else:
                    text = str(data).lower()
                assert "error" in text or "unknown" in text

    async def test_graph_search_missing_query(self):
        """graph action=search without query returns error."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "graph", {"action": "search"}
                )
                data = _parse_result_text(result)
                if isinstance(data, dict):
                    assert "error" in data

    async def test_config_invalid_action(self):
        """config with invalid action returns error."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "config", {"action": "nonexistent"}
                )
                data = _parse_result_text(result)
                if isinstance(data, dict):
                    assert "error" in data
                    assert "valid_actions" in data

    async def test_help_invalid_topic(self):
        """help with invalid topic returns error."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "help", {"topic": "nonexistent_xyz"}
                )
                data = _parse_result_text(result)
                if isinstance(data, dict):
                    assert "error" in data or "valid_topics" in data
                elif isinstance(data, str):
                    text = data.lower()
                    assert "error" in text or "not found" in text or len(text) == 0
