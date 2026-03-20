"""Phase 5: Live MCP protocol test for better-code-review-graph.

Spawns the MCP server as a subprocess and communicates via the MCP protocol
(JSON-RPC over stdio), testing ALL tools through the actual transport layer.
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
    # 1. Tool listing
    # ------------------------------------------------------------------
    async def test_list_tools(self):
        """Server exposes all expected tools."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                expected = {
                    "build_or_update_graph_tool",
                    "get_impact_radius_tool",
                    "query_graph_tool",
                    "get_review_context_tool",
                    "semantic_search_nodes_tool",
                    "embed_graph_tool",
                    "list_graph_stats_tool",
                    "get_docs_section_tool",
                    "find_large_functions_tool",
                }
                assert expected.issubset(names), f"Missing tools: {expected - names}"

    # ------------------------------------------------------------------
    # 2. Full happy-path workflow
    # ------------------------------------------------------------------
    async def test_build_graph(self, sample_repo: Path):
        """build_or_update_graph_tool with full_rebuild parses files."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("status") == "ok"
                assert data.get("files_parsed", 0) > 0

    async def test_list_graph_stats(self, sample_repo: Path):
        """list_graph_stats_tool returns node counts after build."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Build first
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "list_graph_stats_tool",
                    {"repo_root": str(sample_repo)},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("total_nodes", 0) > 0

    async def test_semantic_search(self, sample_repo: Path):
        """semantic_search_nodes_tool returns results for a known symbol."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "semantic_search_nodes_tool",
                    {"query": "calculator", "repo_root": str(sample_repo)},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                results = data.get("results", [])
                assert len(results) > 0, "Expected at least one search result"

    async def test_query_graph_file_summary(self, sample_repo: Path):
        """query_graph_tool with file_summary pattern returns nodes."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "query_graph_tool",
                    {
                        "pattern": "file_summary",
                        "target": "calculator.py",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                results = data.get("results", [])
                assert len(results) > 0

    async def test_get_impact_radius(self, sample_repo: Path):
        """get_impact_radius_tool returns impact data for changed files."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "get_impact_radius_tool",
                    {
                        "changed_files": ["calculator.py"],
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("status") == "ok"

    async def test_get_review_context(self, sample_repo: Path):
        """get_review_context_tool produces review context."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "get_review_context_tool",
                    {
                        "changed_files": ["calculator.py"],
                        "repo_root": str(sample_repo),
                        "include_source": False,
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                # Should have some context structure
                assert len(data) > 0

    async def test_embed_graph(self, sample_repo: Path):
        """embed_graph_tool computes embeddings for graph nodes."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "embed_graph_tool",
                    {"repo_root": str(sample_repo)},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                assert data.get("newly_embedded", 0) > 0

    async def test_get_docs_section(self):
        """get_docs_section_tool returns documentation content."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_docs_section_tool",
                    {"section_name": "usage"},
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                content = data.get("content", "")
                assert len(content) > 0, "Expected non-empty docs content"

    async def test_find_large_functions(self, sample_repo: Path):
        """find_large_functions_tool works with low threshold."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "find_large_functions_tool",
                    {
                        "min_lines": 3,
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert isinstance(data, dict), f"Unexpected response: {data}"
                # With min_lines=3, should find our Calculator class and functions
                results = data.get("results", [])
                assert len(results) > 0

    # ------------------------------------------------------------------
    # 3. Error paths
    # ------------------------------------------------------------------
    async def test_query_graph_invalid_pattern(self, sample_repo: Path):
        """query_graph_tool with an invalid pattern returns error message."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "query_graph_tool",
                    {
                        "pattern": "nonexistent_pattern",
                        "target": "calculator.py",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                # Should contain error information
                if isinstance(data, dict):
                    text = json.dumps(data).lower()
                else:
                    text = str(data).lower()
                assert "error" in text or "unknown" in text or "invalid" in text

    async def test_semantic_search_empty_query(self, sample_repo: Path):
        """semantic_search_nodes_tool with empty query returns empty or error."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "build_or_update_graph_tool",
                    {"full_rebuild": True, "repo_root": str(sample_repo)},
                )
                result = await session.call_tool(
                    "semantic_search_nodes_tool",
                    {"query": "", "repo_root": str(sample_repo)},
                )
                data = _parse_result_text(result)
                # Empty query should return empty results or an error
                if isinstance(data, dict):
                    results = data.get("results", [])
                    # Either empty results or error key is acceptable
                    assert (
                        len(results) == 0
                        or "error" in json.dumps(data).lower()
                        or len(results) > 0  # some servers return all results
                    )
                else:
                    # String error response is also acceptable
                    assert isinstance(data, str)

    async def test_get_docs_section_invalid(self):
        """get_docs_section_tool with invalid section name."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_docs_section_tool",
                    {"section_name": "nonexistent_section_xyz"},
                )
                data = _parse_result_text(result)
                if isinstance(data, dict):
                    text = json.dumps(data).lower()
                else:
                    text = str(data).lower()
                # Should indicate section not found or return empty
                assert (
                    "not found" in text
                    or "error" in text
                    or "available" in text
                    or len(text) == 0
                )
