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
    diff_graph,
    embed_graph,
    export_graph_dispatch,
    find_large_functions,
    get_docs_section,
    get_impact_radius,
    get_review_context,
    list_graph_stats,
    query_graph,
    renamed_in_diff,
    review_delta,
    security_report,
    security_rule_list,
    security_scan,
    security_suppress,
    semantic_search_nodes,
    spot_check_last_callers,
    summarize_graph_dispatch,
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
        "stats (repo_root), embed (repo_root), "
        "export (format, output_path, repo_root), "
        "summarize (max_nodes, repo_root). "
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
    format: str = "graphml",
    output_path: str | None = None,
    max_nodes: int = 500,
    roots: list[str] | None = None,
) -> str:
    """Build, update, and manage the code knowledge graph.

    Actions (required params -> optional):
    - build (-> full_rebuild=false, base="HEAD~1", repo_root, roots): Parse source and build graph.
        ``roots`` (Phase 2 Task 10) optionally federates additional repo
        directories into the same graph DB; each is registered in the
        :class:`RepoRegistry` and its files are tagged with the
        corresponding ``repo_id``. Pair with ``query`` action's ``repo``
        kwarg to scope subsequent queries.
    - update (-> base="HEAD~1", repo_root): Incremental update (alias for build)
    - stats (-> repo_root): Node/edge counts, languages, embedding status
    - embed (-> repo_root): Compute vector embeddings for semantic search
    - export (-> format='graphml', output_path=None, repo_root): Export graph
        in graphml | json-ld | dot | cypher format. Writes to output_path when
        provided, otherwise returns payload inline.
    - summarize (-> max_nodes=500, repo_root): Generate LLM summaries for
        Function nodes. Provider auto-detected from env (GEMINI_API_KEY >
        GOOGLE_API_KEY > OPENAI_API_KEY); no-op when no provider configured.
        Cost-capped via max_nodes (default 500 LLM calls per invocation).
    """
    match action:
        case "build":
            return _json(
                build_or_update_graph(
                    full_rebuild=full_rebuild,
                    repo_root=repo_root,
                    base=base,
                    roots=roots,
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
        case "export":
            return _json(
                export_graph_dispatch(
                    repo_root=repo_root, format=format, output_path=output_path
                )
            )
        case "summarize":
            return _json(
                summarize_graph_dispatch(repo_root=repo_root, max_nodes=max_nodes)
            )
        case _:
            import difflib

            valid_actions = [
                "build",
                "embed",
                "export",
                "stats",
                "summarize",
                "update",
            ]
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


def _handle_query_action(
    pattern: str | None,
    target: str | None,
    repo_root: str | None,
    languages: list[str] | None,
    repo: str,
    as_of: str,
) -> str:
    """Handle the 'query' action."""
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
            repo=repo,
            as_of=as_of,
        )
    )


def _handle_search_action(
    search_query: str | None,
    kind: str | None,
    limit: int,
    repo_root: str | None,
    repo: str,
    as_of: str,
) -> str:
    """Handle the 'search' action."""
    if not search_query:
        return _json({"error": "search_query is required for search action"})
    result = semantic_search_nodes(
        query=search_query,
        kind=kind,
        limit=limit,
        repo_root=repo_root,
        repo=repo,
        as_of=as_of,
    )
    result = _maybe_include_setup_hint(result)
    return _json(result)


def _handle_impact_action(
    changed_files: list[str] | None,
    max_depth: int,
    max_results: int,
    repo_root: str | None,
    base: str,
    max_payload_bytes: int,
    repo: str,
    as_of: str,
) -> str:
    """Handle the 'impact' action."""
    return _json(
        get_impact_radius(
            changed_files=changed_files,
            max_depth=max_depth,
            max_results=max_results,
            repo_root=repo_root,
            base=base,
            max_payload_bytes=max_payload_bytes,
            repo=repo,
            as_of=as_of,
        )
    )


def _handle_large_functions_action(
    min_lines: int,
    kind: str | None,
    file_path_pattern: str | None,
    limit: int,
    repo_root: str | None,
    repo: str,
) -> str:
    """Handle the 'large_functions' action."""
    return _json(
        find_large_functions(
            min_lines=min_lines,
            kind=kind,
            file_path_pattern=file_path_pattern,
            limit=limit,
            repo_root=repo_root,
            repo=repo,
        )
    )


def _handle_spot_check_action(
    n: int,
    repo_root: str | None,
    context_lines: int,
) -> str:
    """Handle the 'spot_check' action."""
    return _json(
        spot_check_last_callers(
            n=n,
            repo_root=repo_root,
            context_lines=context_lines,
        )
    )


def _handle_renamed_in_diff_action(
    base: str,
    changed_files: list[str] | None,
    repo_root: str | None,
) -> str:
    """Handle the 'renamed_in_diff' action."""
    return _json(
        renamed_in_diff(
            base=base,
            changed_files=changed_files,
            repo_root=repo_root,
        )
    )


def _handle_diff_action(
    repo_root: str | None,
    from_sha: str,
    to_sha: str,
    repo: str,
) -> str:
    """Handle the 'diff' action."""
    return _json(
        diff_graph(
            repo_root=repo_root,
            from_sha=from_sha,
            to_sha=to_sha,
            repo=repo,
        )
    )


def _handle_unknown_action(action: str) -> str:
    """Handle unknown actions."""
    import difflib

    valid_actions = [
        "diff",
        "impact",
        "large_functions",
        "query",
        "renamed_in_diff",
        "search",
        "spot_check",
    ]
    closest = difflib.get_close_matches(action, valid_actions, n=1)
    suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
    return _json(
        {
            "error": f"Unknown action '{action}'.{suggestion}",
            "valid_actions": valid_actions,
        }
    )


@mcp.tool(
    description=(
        "Query the code knowledge graph for relationships, search, and impact analysis. "
        "Actions: query (pattern, target), search (search_query), impact (changed_files|base), "
        "large_functions (min_lines), spot_check (n -- random callsite snippets from "
        "last callers_of/callees_of/inheritors_of/importers_of result), "
        "renamed_in_diff (base -- symbols whose callsite line shifted vs base ref), "
        "diff (from_sha, to_sha -- nodes added/removed/modified between two commit SHAs). "
        "Use `help` tool for full docs."
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
    # spot_check params (#318)
    n: int = 3,
    context_lines: int = 2,
    # common
    repo_root: str | None = None,
    # Phase 2 Task 10 — cross-cutting repo filter
    repo: str = "",
    # Phase 3 Task 9 — temporal cross-cutting params
    as_of: str = "",
    from_sha: str = "",
    to_sha: str = "",
) -> str:
    """Query the code knowledge graph for relationships, search, and impact analysis.

    Actions (required params -> optional):
    - query (pattern, target -> repo_root, languages, repo): Predefined graph queries
      pattern: callers_of | callees_of | imports_of | importers_of | children_of | tests_for | inheritors_of | file_summary
      languages: filter `tests_for` results to listed languages (D16, fixes #340)
      repo: Phase 2 Task 10 — when non-empty, scope to that ``repo_id``
        (e.g. ``repo='repo_a-aaaaaaaa'``). Default ``""`` queries every
        federated repo.
    - search (search_query -> kind, limit=20, repo_root, repo): Search nodes by name/keyword/vector
    - impact (-> changed_files, max_depth=2, max_results=500, base="HEAD~1", repo_root, repo): Blast radius analysis
    - large_functions (-> min_lines=50, kind, file_path_pattern, limit=20, repo_root, repo): Find oversized functions

    For `query` action with `callers_of`/`callees_of`, the `not_found` response
    includes a `reason` field (`no_such_symbol` | `symbol_not_indexed` |
    `ambiguous_unqualified`) plus `indexed_kinds`, `indexed_under`, and `hint`
    advisory fields (D15, fixes #339).
    """
    match action:
        case "query":
            return _handle_query_action(
                pattern=pattern,
                target=target,
                repo_root=repo_root,
                languages=languages,
                repo=repo,
                as_of=as_of,
            )
        case "search":
            return _handle_search_action(
                search_query=search_query,
                kind=kind,
                limit=limit,
                repo_root=repo_root,
                repo=repo,
                as_of=as_of,
            )
        case "impact":
            return _handle_impact_action(
                changed_files=changed_files,
                max_depth=max_depth,
                max_results=max_results,
                repo_root=repo_root,
                base=base,
                max_payload_bytes=max_payload_bytes,
                repo=repo,
                as_of=as_of,
            )
        case "large_functions":
            return _handle_large_functions_action(
                min_lines=min_lines,
                kind=kind,
                file_path_pattern=file_path_pattern,
                limit=limit,
                repo_root=repo_root,
                repo=repo,
            )
        case "spot_check":
            return _handle_spot_check_action(
                n=n,
                repo_root=repo_root,
                context_lines=context_lines,
            )
        case "renamed_in_diff":
            return _handle_renamed_in_diff_action(
                base=base,
                changed_files=changed_files,
                repo_root=repo_root,
            )
        case "diff":
            return _handle_diff_action(
                repo_root=repo_root,
                from_sha=from_sha,
                to_sha=to_sha,
                repo=repo,
            )
        case _:
            return _handle_unknown_action(action)


# ---------------------------------------------------------------------------
# Tool 3: review -- token-efficient code review context
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Generate token-efficient review context for code changes. "
        "Actions: context (default — auto-detects changed files from git diff, returns "
        "structural summary, impacted nodes, source snippets, and review guidance), "
        "delta (from_sha, to_sha — wraps the `query.diff` buckets and, when "
        "show_line_shifts=true, surfaces qualified_names whose line_start moved "
        "between the two commits for refactor auditing). "
        "Context params: changed_files (auto), max_depth=2, include_source=true, max_lines_per_file=200, base='HEAD~1', repo_root (auto). "
        "Delta params: from_sha, to_sha, show_line_shifts=false, repo, repo_root. "
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
    action: str = "context",
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    include_source: bool = True,
    max_lines_per_file: int = 200,
    base: str = "HEAD~1",
    repo_root: str | None = None,
    languages: list[str] | None = None,
    repo: str = "",
    # Phase 3 Task 10 — review.delta params
    from_sha: str = "",
    to_sha: str = "",
    show_line_shifts: bool = False,
) -> str:
    """Generate focused review context for code changes.

    Actions:

    * ``context`` (default): Auto-detects changed files from git diff
      and returns the structural summary + impacted nodes/files +
      source snippets + review guidance produced by
      :func:`get_review_context`. This is the original review tool
      behaviour — calls without an explicit ``action`` continue to
      hit this path.
    * ``delta``: Wraps :func:`review_delta`. Given ``from_sha`` and
      ``to_sha``, returns the ``diff`` buckets (added / removed /
      modified) and, when ``show_line_shifts=True``, an extra
      ``line_shifts`` list of ``{qualified_name, before_line,
      after_line}`` entries for refactor auditing (Phase 3 Task 10).

    Args:
        action: ``context`` (default) or ``delta``.
        changed_files: ``context`` action — files to review (auto-detected
            from git if omitted).
        max_depth: ``context`` action — impact radius depth (default: 2).
        include_source: ``context`` action — include source code snippets
            (default: true).
        max_lines_per_file: ``context`` action — max source lines per file
            (default: 200).
        base: ``context`` action — git ref for change detection
            (default: ``HEAD~1``).
        repo_root: Repository root path (auto-detected). Both actions.
        languages: ``context`` action — optional list of language names
            (e.g. ``["python"]``) to scope the ``untested_functions``
            list. Excludes functions whose language doesn't match. Fixes
            false positives on cross-language repos (D16, fixes #340).
        repo: Phase 2 Task 10 — when non-empty, scope to nodes whose
            ``repo_id`` matches (e.g. ``repo='repo_a-aaaaaaaa'``).
            Default ``""`` includes every federated repo. Both actions.
        from_sha: ``delta`` action — earlier commit SHA. Required.
        to_sha: ``delta`` action — later commit SHA. Required.
        show_line_shifts: ``delta`` action — when True, include nodes
            whose ``line_start`` moved between ``from_sha`` and
            ``to_sha`` in the response (default False).
    """
    match action:
        case "context":
            return _json(
                get_review_context(
                    changed_files=changed_files,
                    max_depth=max_depth,
                    include_source=include_source,
                    max_lines_per_file=max_lines_per_file,
                    repo_root=repo_root,
                    base=base,
                    languages=languages,
                    repo=repo,
                )
            )
        case "delta":
            return _json(
                review_delta(
                    repo_root=repo_root,
                    from_sha=from_sha,
                    to_sha=to_sha,
                    show_line_shifts=show_line_shifts,
                    repo=repo,
                )
            )
        case _:
            import difflib

            valid_actions = ["context", "delta"]
            closest = difflib.get_close_matches(action, valid_actions, n=1)
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return _json(
                {
                    "error": f"Unknown action '{action}'.{suggestion}",
                    "valid_actions": valid_actions,
                }
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
    - recipes: Common operational recipes (#319) -- workflow patterns
      that combine the 5 tools (freshness check, blast radius, scope
      completeness, pre-merge review, etc.)
    """
    valid_topics = {
        "graph": "graph.md",
        "query": "query.md",
        "review": "review.md",
        "config": "config.md",
        "recipes": "recipes.md",
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
# Tool 6: security (Phase 3 Task 5) -- scan / report / suppress / rule_list
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Security scanning over the code knowledge graph. "
        "Actions: scan (engine='heuristic'|'semgrep', repo_root), "
        "report (format='json'|'sarif', repo_root), "
        "suppress (rule_id, remove=false, repo_root), "
        "rule_list (engine='heuristic'|'semgrep'). "
        "Use `help` tool for full docs."
    ),
    annotations=ToolAnnotations(
        title="Security",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def security(
    action: str = "scan",
    repo_root: str | None = None,
    engine: str = "heuristic",
    format: str = "json",
    rule_id: str | None = None,
    remove: bool = False,
) -> str:
    """Security scanning tool: scan / report / suppress / rule_list.

    Actions (required params -> optional):

    - scan (-> engine='heuristic'|'semgrep', repo_root): Run a security scan
      over Function/Class/Method nodes; results are cached on disk and
      persisted to ``nodes.security_tags``.
    - report (-> format='json'|'sarif', repo_root): Re-emit the cached scan
      payload as JSON (default) or SARIF v2.1.0.
    - suppress (rule_id -> remove=false, repo_root): Add or remove a rule_id
      from the persistent suppression list at
      ``.code-review-graph/security-suppressions.json``.
    - rule_list (-> engine='heuristic'|'semgrep'): Enumerate active rules.
    """
    match action:
        case "scan":
            return _json(security_scan(repo_root=repo_root, engine=engine))
        case "report":
            return _json(security_report(repo_root=repo_root, format=format))
        case "suppress":
            return _json(
                security_suppress(repo_root=repo_root, rule_id=rule_id, remove=remove)
            )
        case "rule_list":
            return _json(security_rule_list(engine=engine))
        case _:
            import difflib

            valid_actions = ["report", "rule_list", "scan", "suppress"]
            closest = difflib.get_close_matches(action, valid_actions, n=1)
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return _json(
                {
                    "error": f"Unknown action '{action}'.{suggestion}",
                    "valid_actions": valid_actions,
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
