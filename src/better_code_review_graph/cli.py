"""Console-script entry: mounts the shared mcp_core CLI builder.

Bare invocation and any leading-dash argv (e.g. --http) start the server
exactly as before; a leading positional argv[0] routes to a subcommand
(``graph build|embed``) instead.
"""

from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version


def _version() -> str:
    """Resolve the installed package version, falling back to 'dev'."""
    try:
        return pkg_version("better-code-review-graph")
    except PackageNotFoundError:
        return "dev"


def _serve(argv: list[str]) -> int | None:
    from .server import serve_main

    serve_main()
    return 0


def _configure_graph(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "graph_action", choices=["build", "embed"], help="Graph action to run"
    )
    p.add_argument(
        "--full-rebuild",
        action="store_true",
        default=False,
        help="Re-parse every file (build only; ignored for embed)",
    )
    p.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path (auto-detected if omitted)",
    )
    p.add_argument(
        "--base",
        default="HEAD~1",
        help="Git ref for incremental diff (build only; ignored for embed)",
    )


def _handle_graph(args: argparse.Namespace) -> int:
    if args.graph_action == "build":
        from .tools import build_or_update_graph

        result = build_or_update_graph(
            full_rebuild=args.full_rebuild,
            repo_root=args.repo_root,
            base=args.base,
        )
    else:
        from .tools import embed_graph

        result = embed_graph(repo_root=args.repo_root)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result else 0


def main() -> int:
    from mcp_core import build_cli

    return build_cli(
        "better-code-review-graph",
        serve=_serve,
        extra={"graph": (_configure_graph, _handle_graph)},
        version=_version(),
    )(None)
