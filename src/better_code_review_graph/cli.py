"""CLI entry point for better-code-review-graph.

Usage:
    better-code-review-graph             # Start MCP server (stdio)
    better-code-review-graph --version   # Show version
    better-code-review-graph --repo DIR  # Start with custom repo root
    better-code-review-graph update      # Incremental update (hooks only)
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version as pkg_version


def _get_version() -> str:
    """Get the installed package version."""
    try:
        return pkg_version("better-code-review-graph")
    except Exception:
        return "dev"


def main() -> None:
    """Main CLI entry point — starts the MCP server by default."""
    # Hook-only command: `better-code-review-graph update [--base X] [--repo DIR]`
    if len(sys.argv) >= 2 and sys.argv[1] == "update":
        _run_update()
        return

    ap = argparse.ArgumentParser(
        prog="better-code-review-graph",
        description="Persistent incremental knowledge graph for code reviews",
    )
    ap.add_argument(
        "-v", "--version", action="store_true", help="Show version and exit"
    )
    ap.add_argument("--repo", default=None, help="Repository root (auto-detected)")

    args = ap.parse_args()

    if args.version:
        print(f"better-code-review-graph {_get_version()}")
        return

    from .server import serve_main

    serve_main(repo_root=args.repo)


def _run_update() -> None:
    """Run incremental graph update (called by PostToolUse hook)."""
    import logging
    from pathlib import Path

    # Parse update-specific args
    ap = argparse.ArgumentParser(prog="better-code-review-graph update")
    ap.add_argument("--base", default="HEAD~1", help="Git diff base")
    ap.add_argument("--repo", default=None, help="Repository root")
    args = ap.parse_args(sys.argv[2:])

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    from .graph import GraphStore
    from .incremental import find_repo_root, get_db_path, incremental_update

    repo_root = Path(args.repo) if args.repo else find_repo_root()
    if not repo_root:
        sys.exit(1)

    db_path = get_db_path(repo_root)
    store = GraphStore(db_path)
    try:
        incremental_update(repo_root, store, base=args.base)
    finally:
        store.close()
