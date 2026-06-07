"""Regression test: server reports its own package version in serverInfo.

Previously the FastMCP constructor was called without ``version=``, so the
reported version defaulted to the fastmcp framework version (e.g. "3.4.2")
instead of the better-code-review-graph package version.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from unittest.mock import patch

from better_code_review_graph.server import _resolve_version, mcp


def test_serverinfo_reports_package_version():
    expected = pkg_version("better-code-review-graph")
    reported = mcp._mcp_server.create_initialization_options().server_version
    assert reported == expected


def test_serverinfo_not_fastmcp_version():
    reported = mcp._mcp_server.create_initialization_options().server_version
    fastmcp_version = pkg_version("fastmcp")
    assert reported != fastmcp_version


def test_resolve_version_fallback_when_not_installed():
    with patch(
        "better_code_review_graph.server.pkg_version",
        side_effect=PackageNotFoundError("better-code-review-graph"),
    ):
        assert _resolve_version() == "dev"
