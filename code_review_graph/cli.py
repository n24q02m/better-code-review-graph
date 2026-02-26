"""CLI entry point for code-review-graph.

Usage:
    code-review-graph init
    code-review-graph build [--base BASE]
    code-review-graph update [--base BASE]
    code-review-graph watch
    code-review-graph status
    code-review-graph serve
    code-review-graph visualize
"""

from __future__ import annotations

import sys

# Python version check — must come before any other imports
if sys.version_info < (3, 10):
    print("code-review-graph requires Python 3.10 or higher.")
    print(f"  You are running Python {sys.version}")
    print()
    print("Options:")
    print("  1. Install Python 3.10+: https://www.python.org/downloads/")
    print("  2. Use Docker: docker run -v $(pwd):/repo tirth8205/code-review-graph")
    sys.exit(1)

import argparse
import json
import logging
from pathlib import Path


def _handle_init(args: argparse.Namespace) -> None:
    """Set up .mcp.json in the project root for Claude Code integration."""
    from .incremental import find_repo_root

    repo_root = Path(args.repo) if args.repo else find_repo_root()
    if not repo_root:
        repo_root = Path.cwd()

    mcp_path = repo_root / ".mcp.json"
    python_path = sys.executable

    mcp_config = {
        "mcpServers": {
            "code-review-graph": {
                "command": python_path,
                "args": ["-m", "code_review_graph.main"],
                "cwd": ".",
            }
        }
    }

    # Merge into existing .mcp.json if present
    if mcp_path.exists():
        try:
            existing = json.loads(mcp_path.read_text())
            if "code-review-graph" in existing.get("mcpServers", {}):
                print(f"Already configured in {mcp_path}")
                print(f"  Python: {existing['mcpServers']['code-review-graph']['command']}")
                return
            existing.setdefault("mcpServers", {}).update(mcp_config["mcpServers"])
            mcp_config = existing
        except (json.JSONDecodeError, KeyError):
            pass  # Overwrite malformed file

    mcp_path.write_text(json.dumps(mcp_config, indent=2) + "\n")
    print(f"Created {mcp_path}")
    print(f"  Python: {python_path}")
    print()
    print("Next steps:")
    print(f"  code-review-graph build    # build the knowledge graph")
    print(f"  Restart Claude Code        # to pick up the new MCP server")


def main() -> None:
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(
        prog="code-review-graph",
        description="Persistent incremental knowledge graph for code reviews",
    )
    sub = ap.add_subparsers(dest="command")

    # init
    init_cmd = sub.add_parser(
        "init", help="Set up .mcp.json for Claude Code integration"
    )
    init_cmd.add_argument("--repo", default=None, help="Repository root (auto-detected)")

    # build
    build_cmd = sub.add_parser("build", help="Full graph build (re-parse all files)")
    build_cmd.add_argument("--repo", default=None, help="Repository root (auto-detected)")

    # update
    update_cmd = sub.add_parser("update", help="Incremental update (only changed files)")
    update_cmd.add_argument("--base", default="HEAD~1", help="Git diff base (default: HEAD~1)")
    update_cmd.add_argument("--repo", default=None, help="Repository root (auto-detected)")

    # watch
    watch_cmd = sub.add_parser("watch", help="Watch for changes and auto-update")
    watch_cmd.add_argument("--repo", default=None, help="Repository root (auto-detected)")

    # status
    status_cmd = sub.add_parser("status", help="Show graph statistics")
    status_cmd.add_argument("--repo", default=None, help="Repository root (auto-detected)")

    # visualize
    vis_cmd = sub.add_parser("visualize", help="Generate interactive HTML graph visualization")
    vis_cmd.add_argument("--repo", default=None, help="Repository root (auto-detected)")

    # serve
    sub.add_parser("serve", help="Start MCP server (stdio transport)")

    args = ap.parse_args()

    if not args.command:
        ap.print_help()
        sys.exit(1)

    if args.command == "serve":
        from .main import main as serve_main
        serve_main()
        return

    if args.command == "init":
        _handle_init(args)
        return

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from .graph import GraphStore
    from .incremental import (
        find_repo_root,
        full_build,
        get_db_path,
        incremental_update,
        watch,
    )

    repo_root = Path(args.repo) if args.repo else find_repo_root()
    if not repo_root:
        logging.error("Not in a git repository. Run from a project directory or pass --repo.")
        sys.exit(1)

    db_path = get_db_path(repo_root)
    store = GraphStore(db_path)

    try:
        if args.command == "build":
            result = full_build(repo_root, store)
            print(
                f"Full build: {result['files_parsed']} files, "
                f"{result['total_nodes']} nodes, {result['total_edges']} edges"
            )
            if result["errors"]:
                print(f"Errors: {len(result['errors'])}")

        elif args.command == "update":
            result = incremental_update(repo_root, store, base=args.base)
            print(
                f"Incremental: {result['files_updated']} files updated, "
                f"{result['total_nodes']} nodes, {result['total_edges']} edges"
            )

        elif args.command == "status":
            stats = store.get_stats()
            print(f"Nodes: {stats.total_nodes}")
            print(f"Edges: {stats.total_edges}")
            print(f"Files: {stats.files_count}")
            print(f"Languages: {', '.join(stats.languages)}")
            print(f"Last updated: {stats.last_updated or 'never'}")

        elif args.command == "watch":
            watch(repo_root, store)

        elif args.command == "visualize":
            from .visualization import generate_html
            html_path = repo_root / ".code-review-graph.html"
            generate_html(store, html_path)
            print(f"Visualization: {html_path}")
            print("Open in browser to explore your codebase graph.")

    finally:
        store.close()
