"""CLI entry point -- starts MCP server."""

from __future__ import annotations


def main() -> None:
    """Main CLI entry point -- starts the MCP server."""
    from .server import serve_main

    serve_main()
