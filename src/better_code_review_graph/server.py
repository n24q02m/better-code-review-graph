"""MCP server entry point for Better Code Review Graph.

3-tier tool architecture: graph (mega-tool) + config + help.
Run as: better-code-review-graph serve
"""

from __future__ import annotations

import json
from importlib.resources import files

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .embeddings import EmbeddingStore, init_backend, resolve_backend
from .incremental import get_db_path
from .tools import (
    build_or_update_graph,
    embed_graph,
    find_large_functions,
    get_docs_section,
    get_impact_radius,
    get_review_context,
    list_graph_stats,
    query_graph,
    semantic_search_nodes,
)

_default_repo_root: str | None = None


def _json(obj: object) -> str:
    """Serialize to JSON string."""
    return json.dumps(obj, indent=2)


mcp = FastMCP(
    "better-code-review-graph",
    instructions=(
        "Persistent incremental knowledge graph for token-efficient, "
        "context-aware code reviews. 3 tools: graph (build/query/search/review), "
        "config (status/set), help (full docs). "
        "Use `help` tool for complete documentation."
    ),
)


# ---------------------------------------------------------------------------
# Tool 1: graph (mega-tool — 9 actions)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Code knowledge graph operations. "
        "Actions: build|update|query|search|impact|review|embed|stats|large_functions. "
        "Use `help` tool for full documentation."
    ),
    annotations=ToolAnnotations(
        title="Graph",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def graph(
    action: str,
    # build/update params
    full_rebuild: bool = False,
    base: str = "HEAD~1",
    # query params
    pattern: str | None = None,
    target: str | None = None,
    # search params
    query: str | None = None,
    kind: str | None = None,
    limit: int = 20,
    # impact/review params
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    max_results: int = 500,
    include_source: bool = True,
    max_lines_per_file: int = 200,
    # large_functions params
    min_lines: int = 50,
    file_path_pattern: str | None = None,
    # common
    repo_root: str | None = None,
) -> str:
    """Code knowledge graph operations.

    Actions:
    - build: Full or incremental graph build (full_rebuild, base, repo_root)
    - update: Alias for build with full_rebuild=False
    - query: Run predefined graph queries (pattern, target, repo_root)
      Patterns: callers_of|callees_of|imports_of|importers_of|children_of|tests_for|inheritors_of|file_summary
    - search: Search nodes by name/keyword/vector (query, kind, limit, repo_root)
    - impact: Blast radius of changed files (changed_files, max_depth, max_results, base, repo_root)
    - review: Token-efficient review context (changed_files, max_depth, include_source, max_lines_per_file, base, repo_root)
    - embed: Compute vector embeddings for semantic search (repo_root)
    - stats: Graph statistics (repo_root)
    - large_functions: Find oversized functions/classes (min_lines, kind, file_path_pattern, limit, repo_root)
    """
    match action:
        case "build":
            return _json(
                build_or_update_graph(
                    full_rebuild=full_rebuild, repo_root=repo_root, base=base
                )
            )

        case "update":
            return _json(
                build_or_update_graph(
                    full_rebuild=False, repo_root=repo_root, base=base
                )
            )

        case "query":
            if not pattern:
                return _json(
                    {
                        "error": "pattern is required for query action",
                        "valid_patterns": [
                            "callers_of",
                            "callees_of",
                            "imports_of",
                            "importers_of",
                            "children_of",
                            "tests_for",
                            "inheritors_of",
                            "file_summary",
                        ],
                    }
                )
            if not target:
                return _json({"error": "target is required for query action"})
            return _json(
                query_graph(pattern=pattern, target=target, repo_root=repo_root)
            )

        case "search":
            if not query:
                return _json({"error": "query is required for search action"})
            return _json(
                semantic_search_nodes(
                    query=query, kind=kind, limit=limit, repo_root=repo_root
                )
            )

        case "impact":
            return _json(
                get_impact_radius(
                    changed_files=changed_files,
                    max_depth=max_depth,
                    max_results=max_results,
                    repo_root=repo_root,
                    base=base,
                )
            )

        case "review":
            return _json(
                get_review_context(
                    changed_files=changed_files,
                    max_depth=max_depth,
                    include_source=include_source,
                    max_lines_per_file=max_lines_per_file,
                    repo_root=repo_root,
                    base=base,
                )
            )

        case "embed":
            return _json(embed_graph(repo_root=repo_root))

        case "stats":
            return _json(list_graph_stats(repo_root=repo_root))

        case "large_functions":
            return _json(
                find_large_functions(
                    min_lines=min_lines,
                    kind=kind,
                    file_path_pattern=file_path_pattern,
                    limit=limit,
                    repo_root=repo_root,
                )
            )

        case _:
            return _json(
                {
                    "error": f"Unknown action: {action}",
                    "valid_actions": [
                        "build",
                        "update",
                        "query",
                        "search",
                        "impact",
                        "review",
                        "embed",
                        "stats",
                        "large_functions",
                    ],
                }
            )


# ---------------------------------------------------------------------------
# Tool 2: config (status, set, cache_clear)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Server configuration and status. "
        "Actions: status|set|cache_clear. "
        "Use `help` tool for full documentation."
    ),
    annotations=ToolAnnotations(
        title="Config",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def config(
    action: str,
    key: str | None = None,
    value: str | None = None,
    repo_root: str | None = None,
) -> str:
    """Server configuration and status.

    Actions:
    - status: Show graph path, node/edge counts, embedding backend, last updated
    - set: Update runtime setting (key + value). Keys: log_level
    - cache_clear: Wipe all embeddings from the graph
    """
    match action:
        case "status":
            return _config_status(repo_root)

        case "set":
            if not key:
                return _json(
                    {
                        "error": "key is required for set action",
                        "valid_keys": ["log_level"],
                    }
                )
            if value is None:
                return _json({"error": "value is required for set action"})
            return _config_set(key, value)

        case "cache_clear":
            return _config_cache_clear(repo_root)

        case _:
            return _json(
                {
                    "error": f"Unknown action: {action}",
                    "valid_actions": ["status", "set", "cache_clear"],
                }
            )


def _config_status(repo_root: str | None) -> str:
    """Return server status as JSON."""
    from importlib.metadata import version as pkg_version

    from .tools import _get_store

    try:
        version = pkg_version("better-code-review-graph")
    except Exception:
        version = "dev"

    try:
        store, root = _get_store(repo_root)
        try:
            stats = store.get_stats()
            db_path = get_db_path(root)
            backend = init_backend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                emb_count = emb_store.count()
            finally:
                emb_store.close()

            return _json(
                {
                    "status": "ok",
                    "version": version,
                    "graph_path": str(db_path),
                    "embedding_backend": resolve_backend(),
                    "total_nodes": stats.total_nodes,
                    "total_edges": stats.total_edges,
                    "files_count": stats.files_count,
                    "languages": stats.languages,
                    "embeddings_count": emb_count,
                    "last_updated": stats.last_updated,
                }
            )
        finally:
            store.close()
    except (RuntimeError, ValueError):
        return _json(
            {
                "status": "ok",
                "version": version,
                "graph_path": None,
                "embedding_backend": resolve_backend(),
                "total_nodes": 0,
                "total_edges": 0,
                "message": "No graph found. Run graph action=build first.",
            }
        )


def _config_set(key: str, value: str) -> str:
    """Update a runtime setting."""
    import logging

    valid_keys = {"log_level"}
    if key not in valid_keys:
        return _json({"error": f"Invalid key: {key}", "valid_keys": sorted(valid_keys)})

    if key == "log_level":
        level = value.upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            return _json(
                {
                    "error": f"Invalid log level: {value}",
                    "valid_levels": [
                        "DEBUG",
                        "INFO",
                        "WARNING",
                        "ERROR",
                        "CRITICAL",
                    ],
                }
            )
        logging.getLogger().setLevel(level)
        return _json({"status": "updated", "key": key, "value": level})

    # Unreachable: valid_keys guard above catches all unknown keys
    return _json({"error": f"Unhandled key: {key}"})  # pragma: no cover


def _config_cache_clear(repo_root: str | None) -> str:
    """Clear all embeddings from the graph."""
    from .tools import _get_store

    try:
        store, root = _get_store(repo_root)
        try:
            db_path = get_db_path(root)
            backend = init_backend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                count_before = emb_store.count()
                emb_store.clear()
                return _json(
                    {
                        "status": "cache cleared",
                        "embeddings_removed": count_before,
                    }
                )
            finally:
                emb_store.close()
        finally:
            store.close()
    except (RuntimeError, ValueError):
        return _json({"status": "cache cleared", "embeddings_removed": 0})


# ---------------------------------------------------------------------------
# Tool 3: help (documentation)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Full documentation for graph and config tools. "
        "Topics: graph|config. "
        "Use when compressed tool descriptions are insufficient."
    ),
    annotations=ToolAnnotations(
        title="Help",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def help(topic: str = "graph") -> str:
    """Load full documentation for a tool.

    Topics:
    - graph: All 9 graph actions with parameters and examples
    - config: Config actions (status, set, cache_clear)
    """
    valid_topics = {"graph": "graph.md", "config": "config.md"}
    filename = valid_topics.get(topic)
    if not filename:
        return _json(
            {"error": f"Invalid topic: {topic}", "valid_topics": sorted(valid_topics)}
        )

    try:
        doc_file = files("better_code_review_graph.docs").joinpath(filename)
        return doc_file.read_text()
    except (FileNotFoundError, ModuleNotFoundError):
        # Fallback: try loading the old LLM-OPTIMIZED-REFERENCE.md sections
        if topic == "graph":
            result = get_docs_section(
                section_name="commands", repo_root=_default_repo_root
            )
            if result.get("status") == "ok":
                return result["content"]
        return _json(
            {
                "error": f"Documentation not found for topic: {topic}",
                "valid_topics": sorted(valid_topics),
            }
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def serve_main(repo_root: str | None = None) -> None:
    """Run the MCP server via stdio."""
    global _default_repo_root
    _default_repo_root = repo_root
    mcp.run(transport="stdio")


if __name__ == "__main__":
    serve_main()
