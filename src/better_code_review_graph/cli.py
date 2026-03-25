"""CLI entry point -- starts MCP server."""

from __future__ import annotations

import asyncio
import logging


def main() -> None:
    """Main CLI entry point -- starts the MCP server."""
    from .relay_setup import ensure_config
    from .server import serve_main

    try:
        asyncio.run(ensure_config())
    except Exception:
        logging.getLogger(__name__).debug(
            "Relay setup skipped (non-fatal)", exc_info=True
        )

    serve_main()
