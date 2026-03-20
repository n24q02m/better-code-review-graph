"""CLI entry point for better-code-review-graph.

Usage:
    better-code-review-graph          # Show version + usage
    better-code-review-graph serve    # Start MCP server (stdio)
    better-code-review-graph update   # Incremental graph update (for hooks)
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
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(
        prog="better-code-review-graph",
        description="Persistent incremental knowledge graph for code reviews",
    )
    ap.add_argument(
        "-v", "--version", action="store_true", help="Show version and exit"
    )
    sub = ap.add_subparsers(dest="command")

    serve_cmd = sub.add_parser("serve", help="Start MCP server (stdio transport)")
    serve_cmd.add_argument(
        "--repo", default=None, help="Repository root (auto-detected)"
    )

    update_cmd = sub.add_parser(
        "update", help="Incremental graph update (used by hooks)"
    )
    update_cmd.add_argument(
        "--base", default="HEAD~1", help="Git diff base (default: HEAD~1)"
    )
    update_cmd.add_argument(
        "--repo", default=None, help="Repository root (auto-detected)"
    )

    args = ap.parse_args()

    if args.version:
        print(f"better-code-review-graph {_get_version()}")
        return

    if args.command == "serve":
        from .server import serve_main

        serve_main(repo_root=args.repo)
        return

    if args.command == "update":
        _run_update(args)
        return

    # No command: show version + usage
    print(f"better-code-review-graph {_get_version()}")
    print()
    print("Usage: better-code-review-graph serve")
    print()
    print("All graph operations are available through MCP tools:")
    print("  graph action=build       Build the knowledge graph")
    print("  graph action=update      Incremental update")
    print("  graph action=query       Query code relationships")
    print("  graph action=search      Search nodes")
    print("  graph action=stats       View graph statistics")
    print("  config action=status     Server status")


def _run_update(args: argparse.Namespace) -> None:
    """Run incremental graph update (called by PostToolUse hook)."""
    import logging
    from pathlib import Path

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
