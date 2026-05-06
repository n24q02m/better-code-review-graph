"""MCP server entry point for Better Code Review Graph.

5-tool architecture: graph + query + review (3 main) + config + help.
Run as: better-code-review-graph serve
"""

from __future__ import annotations

import json
import os
from importlib.resources import files

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mcp_core.relay.tool_helpers import register_open_relay_tool

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


def _maybe_include_setup_hint(result: dict) -> dict:
    """If in awaiting_setup, add hint about cloud setup to response."""
    from .credential_state import CredentialState, get_setup_url, get_state

    if get_state() == CredentialState.AWAITING_SETUP:
        url = get_setup_url()
        if url:
            result["_setup_hint"] = (
                f"Cloud embeddings available. Configure API keys: {url}"
            )
        else:
            result["_setup_hint"] = (
                "Cloud embeddings available. Use config(action='setup_start') to configure."
            )
    return result


mcp = FastMCP(
    "better-code-review-graph",
    instructions=(
        "Persistent incremental knowledge graph for token-efficient, "
        "context-aware code reviews. 5 tools: graph (build/embed/stats), "
        "query (search/impact/patterns), review (code review context), "
        "config (status/set/setup_*), help (full docs)."
    ),
)


# ---------------------------------------------------------------------------
# Tool 1: graph -- lifecycle (build, update, stats, embed)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Build and manage the code knowledge graph. "
        "Actions: build (full_rebuild, base, repo_root), update (base, repo_root), "
        "stats (repo_root), embed (repo_root). "
        "Use `help` tool for full docs."
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
    full_rebuild: bool = False,
    base: str = "HEAD~1",
    repo_root: str | None = None,
) -> str:
    """Build, update, and manage the code knowledge graph.

    Actions (required params -> optional):
    - build (-> full_rebuild=false, base="HEAD~1", repo_root): Parse source and build graph
    - update (-> base="HEAD~1", repo_root): Incremental update (alias for build)
    - stats (-> repo_root): Node/edge counts, languages, embedding status
    - embed (-> repo_root): Compute vector embeddings for semantic search
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
        case "stats":
            return _json(list_graph_stats(repo_root=repo_root))
        case "embed":
            result = embed_graph(repo_root=repo_root)
            result = _maybe_include_setup_hint(result)
            return _json(result)
        case _:
            import difflib

            valid_actions = ["build", "embed", "stats", "update"]
            closest = difflib.get_close_matches(action, valid_actions, n=1)
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return _json(
                {
                    "error": f"Unknown action '{action}'.{suggestion}",
                    "valid_actions": valid_actions,
                }
            )


# ---------------------------------------------------------------------------
# Tool 2: query -- read operations (query, search, impact, large_functions)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Query the code knowledge graph for relationships, search, and impact analysis. "
        "Actions: query (pattern, target), search (search_query), impact (changed_files|base), "
        "large_functions (min_lines). Use `help` tool for full docs."
    ),
    annotations=ToolAnnotations(
        title="Query",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def query(
    action: str,
    # query params
    pattern: str | None = None,
    target: str | None = None,
    # search params
    search_query: str | None = None,
    kind: str | None = None,
    limit: int = 20,
    # impact params
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    max_results: int = 500,
    max_payload_bytes: int = 500_000,
    base: str = "HEAD~1",
    # large_functions params
    min_lines: int = 50,
    file_path_pattern: str | None = None,
    # tests_for params (D16)
    languages: list[str] | None = None,
    # common
    repo_root: str | None = None,
) -> str:
    """Query the code knowledge graph for relationships, search, and impact analysis.

    Actions (required params -> optional):
    - query (pattern, target -> repo_root, languages): Predefined graph queries
      pattern: callers_of | callees_of | imports_of | importers_of | children_of | tests_for | inheritors_of | file_summary
      languages: filter `tests_for` results to listed languages (D16, fixes #340)
    - search (search_query -> kind, limit=20, repo_root): Search nodes by name/keyword/vector
    - impact (-> changed_files, max_depth=2, max_results=500, base="HEAD~1", repo_root): Blast radius analysis
    - large_functions (-> min_lines=50, kind, file_path_pattern, limit=20, repo_root): Find oversized functions

    For `query` action with `callers_of`/`callees_of`, the `not_found` response
    includes a `reason` field (`no_such_symbol` | `symbol_not_indexed` |
    `ambiguous_unqualified`) plus `indexed_kinds`, `indexed_under`, and `hint`
    advisory fields (D15, fixes #339).
    """
    match action:
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
                query_graph(
                    pattern=pattern,
                    target=target,
                    repo_root=repo_root,
                    languages=languages,
                )
            )
        case "search":
            if not search_query:
                return _json({"error": "search_query is required for search action"})
            result = semantic_search_nodes(
                query=search_query, kind=kind, limit=limit, repo_root=repo_root
            )
            result = _maybe_include_setup_hint(result)
            return _json(result)
        case "impact":
            return _json(
                get_impact_radius(
                    changed_files=changed_files,
                    max_depth=max_depth,
                    max_results=max_results,
                    repo_root=repo_root,
                    base=base,
                    max_payload_bytes=max_payload_bytes,
                )
            )
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
            import difflib

            valid_actions = ["impact", "large_functions", "query", "search"]
            closest = difflib.get_close_matches(action, valid_actions, n=1)
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return _json(
                {
                    "error": f"Unknown action '{action}'.{suggestion}",
                    "valid_actions": valid_actions,
                }
            )


# ---------------------------------------------------------------------------
# Tool 3: review -- token-efficient code review context
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Generate token-efficient review context for code changes. "
        "Auto-detects changed files from git diff. Returns structural summary, "
        "impacted nodes, source snippets, and review guidance. "
        "Params: changed_files (auto), max_depth=2, include_source=true, max_lines_per_file=200, base='HEAD~1', repo_root (auto). "
        "Use `help` tool for full docs."
    ),
    annotations=ToolAnnotations(
        title="Review",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def review(
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    include_source: bool = True,
    max_lines_per_file: int = 200,
    base: str = "HEAD~1",
    repo_root: str | None = None,
    languages: list[str] | None = None,
) -> str:
    """Generate focused review context for code changes.

    Auto-detects changed files from git diff. Returns structural summary,
    impacted nodes/files, source snippets, and review guidance.

    Args:
        changed_files: Files to review (auto-detected from git if omitted)
        max_depth: Impact radius depth (default: 2)
        include_source: Include source code snippets (default: true)
        max_lines_per_file: Max source lines per file (default: 200)
        base: Git ref for change detection (default: HEAD~1)
        repo_root: Repository root path (auto-detected)
        languages: Optional list of language names (e.g. ``["python"]``) to
            scope the ``untested_functions`` list. Excludes functions whose
            language doesn't match. Fixes false positives on cross-language
            repos (D16, fixes #340).
    """
    return _json(
        get_review_context(
            changed_files=changed_files,
            max_depth=max_depth,
            include_source=include_source,
            max_lines_per_file=max_lines_per_file,
            repo_root=repo_root,
            base=base,
            languages=languages,
        )
    )


# ---------------------------------------------------------------------------
# Tool 4: config (status, set, cache_clear, setup_*)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Server configuration, status, and credential setup. "
        "Actions: status (show state), set (key, value -- keys: log_level), "
        "cache_clear (wipe embeddings), "
        "setup_status (credential state), setup_start (relay browser setup), "
        "setup_skip (local mode), setup_reset (clear credentials), "
        "setup_complete (re-resolve from env). "
        "Use `help` tool for full docs."
    ),
    annotations=ToolAnnotations(
        title="Config",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def config(
    action: str,
    key: str | None = None,
    value: str | None = None,
    repo_root: str | None = None,
    force: bool = False,
) -> str:
    """Server configuration, status, and credential setup.

    Config actions:
    - status: Show graph path, node/edge counts, embedding backend, last updated
    - set: Update runtime setting (key + value). Keys: log_level
    - cache_clear: Wipe all embeddings from the graph

    Setup actions:
    - setup_status: Show current credential state and setup URL
    - setup_start: Start relay setup to configure API keys via browser
    - setup_skip: Set local mode (skip relay permanently)
    - setup_reset: Clear credentials and reset to awaiting_setup
    - setup_complete: Re-resolve credentials from env vars
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
        case "setup_status":
            from mcp_core.storage.per_plugin_store import PerPluginStore

            from . import credential_state as _cs

            # Derive providers_configured from live PerPluginStore load + env
            # so status is accurate even if module-level _state is stale.
            _saved = PerPluginStore(_cs.PLUGIN_NAME).load() or {}
            _env_keys = [k for k in _cs.CLOUD_KEYS if os.environ.get(k)]
            _store_keys = [k for k in _cs.CLOUD_KEYS if _saved.get(k)]
            _providers = list(dict.fromkeys(_env_keys + _store_keys))
            if _providers:
                _derived_state = "configured"
            elif _cs.get_state() == _cs.CredentialState.LOCAL:
                _derived_state = "local"
            else:
                _derived_state = "awaiting_setup"
            return _json(
                {
                    "state": _derived_state,
                    "setup_url": _cs.get_setup_url(),
                    "cloud_keys_in_env": _env_keys,
                    "providers_configured": _providers,
                }
            )
        case "setup_start":
            from .credential_state import CredentialState, get_state

            if get_state() == CredentialState.CONFIGURED and not force:
                return _json(
                    {
                        "status": "already_configured",
                        "message": "Already configured. Use force=true to reconfigure.",
                    }
                )
            # In stdio mode (default after spec 2026-05-01) the server reads
            # API keys from env vars only; the browser-based relay form is
            # served by the HTTP-mode entry point at <PUBLIC_URL>/authorize.
            public_url = os.environ.get("PUBLIC_URL")
            if public_url:
                url = f"{public_url.rstrip('/')}/authorize"
                return _json(
                    {
                        "status": "setup_started",
                        "setup_url": url,
                        "message": "Open this URL to configure API keys.",
                    }
                )
            return _json(
                {
                    "status": "stdio_mode",
                    "message": (
                        "Stdio mode reads API keys from env vars only. "
                        "Set GEMINI_API_KEY / OPENAI_API_KEY / JINA_AI_API_KEY / "
                        "COHERE_API_KEY in the plugin config, or switch to HTTP "
                        "mode to use the browser-based setup form."
                    ),
                }
            )
        case "setup_skip":
            from mcp_core import set_local_mode

            from .credential_state import CredentialState, set_state

            set_local_mode(SERVER_NAME)
            set_state(CredentialState.LOCAL)
            return _json(
                {
                    "status": "ok",
                    "message": "Local mode set. Relay will not trigger on restart.",
                }
            )
        case "setup_reset":
            from .credential_state import reset_state

            reset_state()
            return _json(
                {
                    "status": "ok",
                    "message": "Credentials cleared. Next tool call will offer setup.",
                }
            )
        case "setup_complete":
            from .credential_state import (
                get_state as _get_state,
            )
            from .credential_state import (
                resolve_credential_state,
            )

            resolve_credential_state()
            state = _get_state()
            return _json(
                {
                    "status": "ok",
                    "state": state.value,
                    "message": "Credential state refreshed.",
                }
            )
        case _:
            import difflib

            valid_actions = [
                "cache_clear",
                "set",
                "setup_complete",
                "setup_reset",
                "setup_skip",
                "setup_start",
                "setup_status",
                "status",
            ]
            closest = difflib.get_close_matches(action, valid_actions, n=1)
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return _json(
                {
                    "error": f"Unknown action '{action}'.{suggestion}",
                    "valid_actions": valid_actions,
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
# Tool 5: help (documentation)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Get full documentation for any tool. "
        "Topics: graph | query | review | config. "
        "Use when compressed descriptions are insufficient."
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
    - graph: Graph lifecycle (build, update, stats, embed)
    - query: Query operations (query, search, impact, large_functions)
    - review: Code review context generation
    - config: Server configuration (status, set, cache_clear)
    """
    valid_topics = {
        "graph": "graph.md",
        "query": "query.md",
        "review": "review.md",
        "config": "config.md",
    }
    filename = valid_topics.get(topic)
    if not filename:
        import difflib

        closest = difflib.get_close_matches(topic, list(valid_topics.keys()), n=1)
        suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
        return _json(
            {
                "error": f"Unknown topic '{topic}'.{suggestion}",
                "valid_topics": sorted(valid_topics),
            }
        )

    try:
        doc_file = files("better_code_review_graph.docs").joinpath(filename)
        return doc_file.read_text()
    except (FileNotFoundError, ModuleNotFoundError):
        if topic in ("graph", "query"):
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
# Constants
# ---------------------------------------------------------------------------

SERVER_NAME = "better-code-review-graph"


# ---------------------------------------------------------------------------
# Tool: config__open_relay (registered via mcp-core helper)
# ---------------------------------------------------------------------------
# Registers the standard ``config__open_relay`` MCP tool so the LLM can
# re-trigger the relay form (e.g. after credential expiry) by tool call.
# In HTTP mode the tool returns ``<PUBLIC_URL>/authorize``; in stdio mode
# it returns ``status: 'stdio_unsupported'`` so the caller can surface a
# "switch to HTTP mode" message. See ``mcp_core.relay.tool_helpers``.
register_open_relay_tool(mcp, SERVER_NAME, os.environ.get("PUBLIC_URL"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_http(port: int = 0) -> None:
    """Run as HTTP server with local OAuth 2.1 AS.

    Always multi-user remote-style (per spec 2026-05-01-stdio-pure-http-multiuser.md).
    Binds ``0.0.0.0:<MCP_PORT|8080>`` when ``PUBLIC_URL`` is set and refuses
    to start without ``MCP_DCR_SERVER_SECRET`` so per-JWT-sub DCR signing is
    enforced. Each authorize-session's JWT ``sub`` scopes credential storage
    and graph DB path.

    For local self-host without ``PUBLIC_URL`` the server still binds
    ``127.0.0.1`` and runs the same multi-user code path with a single
    JWT sub.
    """
    from mcp_core.transport.local_server import run_http_server

    from .credential_state import _current_sub, save_credentials
    from .relay_schema import RELAY_SCHEMA

    public_url = os.environ.get("PUBLIC_URL")
    if public_url:
        if not os.environ.get("MCP_DCR_SERVER_SECRET"):
            raise SystemExit(
                "better-code-review-graph refuses to start: PUBLIC_URL set but "
                "MCP_DCR_SERVER_SECRET missing. Multi-user remote mode "
                "requires the DCR secret."
            )
        host = "0.0.0.0"
        if port == 0:
            port = int(os.environ.get("MCP_PORT", "8080"))
    else:
        host = "127.0.0.1"

    async def _per_request_sub_scope(claims: dict, next_):
        """Bind the verified JWT ``sub`` to a contextvar for this request.

        Mounted only when ``PUBLIC_URL`` is set (multi-user remote mode).
        ``ContextVar.set/reset`` keeps the binding scoped to this request
        even under concurrent in-flight requests on the same event loop.
        """
        token = _current_sub.set(claims.get("sub"))
        try:
            await next_()
        finally:
            _current_sub.reset(token)

    await run_http_server(
        mcp,
        server_name="better-code-review-graph",
        relay_schema=RELAY_SCHEMA,
        port=port,
        host=host,
        on_credentials_saved=save_credentials,
        auth_scope=_per_request_sub_scope if public_url else None,
    )


def serve_main(repo_root: str | None = None) -> None:
    """Run the MCP server. Defaults to stdio; opt in to HTTP via flag/env.

    Stdio mode (default): runs FastMCP stdio server directly. Reads cloud
    API keys from env vars only. Universal MCP client compatibility.

    HTTP mode (opt-in): triggered by ``--http`` argv flag,
    ``MCP_TRANSPORT=http``, or ``TRANSPORT_MODE=http``. Multi-user JWT-sub
    server with browser relay form at ``<PUBLIC_URL>/authorize``.

    See: ~/projects/.superpower/mcp-core/specs/2026-05-01-stdio-pure-http-multiuser.md
    """
    import asyncio
    import sys

    global _default_repo_root
    _default_repo_root = repo_root

    is_http = (
        "--http" in sys.argv
        or os.environ.get("MCP_TRANSPORT") == "http"
        or os.environ.get("TRANSPORT_MODE") == "http"
    )

    if is_http:
        # HTTP mode: resolve credentials so the relay form can hint current
        # state. Stdio mode resolves lazily inside tool calls.
        from .credential_state import resolve_credential_state

        resolve_credential_state()

        asyncio.run(run_http())
        return

    # Stdio mode (default): run FastMCP stdio server directly. No bridge
    # layer. Cloud API keys come from env vars only -- CRG has a local
    # fallback (qwen3-embed ONNX) so missing cloud creds is non-fatal.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    serve_main()
