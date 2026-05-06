"""MCP tool definitions for the Code Review Graph server.

Exposes 9 tools:
1. build_or_update_graph  - full or incremental build
2. get_impact_radius      - blast radius from changed files
3. query_graph            - predefined graph queries
4. get_review_context     - focused subgraph + review prompt
5. semantic_search_nodes  - keyword + vector search across nodes
6. list_graph_stats       - aggregate statistics
7. embed_graph            - compute vector embeddings for semantic search
8. get_docs_section       - token-optimized documentation retrieval
9. find_large_functions   - find oversized functions/classes by line count
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .embeddings import (
    EmbeddingStore,
    embed_all_nodes,
    init_backend,
    resolve_backend,
    semantic_search,
)
from .graph import GraphStore, edge_to_dict, node_to_dict
from .incremental import (
    find_project_root,
    full_build,
    get_changed_files,
    get_db_path,
    get_staged_and_unstaged,
    incremental_update,
)

# Common JS/TS builtin method names filtered from callers_of results.
# "Who calls .map()?" returns hundreds of hits and is never useful.
# These are kept in the graph (callees_of still shows them) but excluded
# when doing reverse call tracing to reduce noise.
_BUILTIN_CALL_NAMES: set[str] = {
    "map",
    "filter",
    "reduce",
    "reduceRight",
    "forEach",
    "find",
    "findIndex",
    "some",
    "every",
    "includes",
    "indexOf",
    "lastIndexOf",
    "push",
    "pop",
    "shift",
    "unshift",
    "splice",
    "slice",
    "concat",
    "join",
    "flat",
    "flatMap",
    "sort",
    "reverse",
    "fill",
    "keys",
    "values",
    "entries",
    "from",
    "isArray",
    "of",
    "at",
    "trim",
    "trimStart",
    "trimEnd",
    "split",
    "replace",
    "replaceAll",
    "match",
    "matchAll",
    "search",
    "substring",
    "substr",
    "toLowerCase",
    "toUpperCase",
    "startsWith",
    "endsWith",
    "padStart",
    "padEnd",
    "repeat",
    "charAt",
    "charCodeAt",
    "assign",
    "freeze",
    "defineProperty",
    "getOwnPropertyNames",
    "hasOwnProperty",
    "create",
    "is",
    "fromEntries",
    "log",
    "warn",
    "error",
    "info",
    "debug",
    "trace",
    "dir",
    "table",
    "time",
    "timeEnd",
    "assert",
    "clear",
    "count",
    "then",
    "catch",
    "finally",
    "resolve",
    "reject",
    "all",
    "allSettled",
    "race",
    "any",
    "parse",
    "stringify",
    "floor",
    "ceil",
    "round",
    "random",
    "max",
    "min",
    "abs",
    "pow",
    "sqrt",
    "addEventListener",
    "removeEventListener",
    "querySelector",
    "querySelectorAll",
    "getElementById",
    "createElement",
    "appendChild",
    "removeChild",
    "setAttribute",
    "getAttribute",
    "preventDefault",
    "stopPropagation",
    "setTimeout",
    "clearTimeout",
    "setInterval",
    "clearInterval",
    "toString",
    "valueOf",
    "toJSON",
    "toISOString",
    "getTime",
    "getFullYear",
    "now",
    "isNaN",
    "parseInt",
    "parseFloat",
    "toFixed",
    "encodeURIComponent",
    "decodeURIComponent",
    "call",
    "apply",
    "bind",
    "next",
    "emit",
    "on",
    "off",
    "once",
    "pipe",
    "write",
    "read",
    "end",
    "close",
    "destroy",
    "send",
    "status",
    "json",
    "redirect",
    "set",
    "get",
    "delete",
    "has",
    "findUnique",
    "findFirst",
    "findMany",
    "createMany",
    "update",
    "updateMany",
    "deleteMany",
    "upsert",
    "aggregate",
    "groupBy",
    "transaction",
    "describe",
    "it",
    "test",
    "expect",
    "beforeEach",
    "afterEach",
    "beforeAll",
    "afterAll",
    "mock",
    "spyOn",
    "require",
    "fetch",
}


def _build_response_header(
    store: GraphStore | None,
    db_path: Path | None,
    *,
    keyword_only: bool | None = None,
) -> dict[str, Any]:
    """Build a metadata header for ``search`` / ``query`` responses (#330).

    Surfaces ``embeddings_count`` and the derived ``keyword_only`` flag so
    consumers know whether the results came from semantic-similarity search
    (``embeddings_count > 0``) or keyword-substring fallback. Plus
    ``graph_last_updated`` when available. Errors are swallowed and the
    relevant fields fall back to ``None`` -- the header is best-effort
    metadata, never load-bearing for query correctness.

    Args:
        store: Open ``GraphStore`` (used for ``last_updated`` metadata).
        db_path: Path to the graph DB (used to open an EmbeddingStore).
        keyword_only: Optional explicit override (e.g. ``search`` already
            knows whether it ran semantic vs keyword). When ``None`` the
            flag is derived from ``embeddings_count``.
    """
    emb_count: int | None = None
    if db_path is not None:
        try:
            backend = init_backend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                emb_count = emb_store.count()
            finally:
                emb_store.close()
        except Exception:
            emb_count = None

    last_updated: str | None = None
    if store is not None:
        try:
            last_updated = store.get_metadata("last_updated")
        except Exception:
            last_updated = None

    if keyword_only is None:
        keyword_only = (emb_count is None) or (emb_count == 0)

    return {
        "embeddings_count": emb_count if emb_count is not None else 0,
        "keyword_only": bool(keyword_only),
        "graph_last_updated": last_updated,
    }


def _validate_repo_root(path: Path) -> Path:
    """Validate that a path is a plausible project root.

    Ensures the path is an existing directory that contains a ``.git``
    or ``.code-review-graph`` directory, preventing arbitrary file-system
    traversal via the ``repo_root`` parameter.
    """
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"repo_root is not an existing directory: {resolved}")
    if (
        not (resolved / ".git").exists()
        and not (resolved / ".code-review-graph").exists()
    ):
        raise ValueError(
            f"repo_root does not look like a project root (no .git or "
            f".code-review-graph directory found): {resolved}"
        )
    return resolved


def _get_store(repo_root: str | None = None) -> tuple[GraphStore, Path]:
    """Resolve repo root and open the graph store."""
    root = _validate_repo_root(Path(repo_root)) if repo_root else find_project_root()
    db_path = get_db_path(root)
    return GraphStore(db_path), root


# ---------------------------------------------------------------------------
# Tool 1: build_or_update_graph
# ---------------------------------------------------------------------------


def build_or_update_graph(
    full_rebuild: bool = False,
    repo_root: str | None = None,
    base: str = "HEAD~1",
) -> dict[str, Any]:
    """Build or incrementally update the code knowledge graph.

    Args:
        full_rebuild: If True, re-parse every file. If False (default),
                      only re-parse files changed since `base`.
        repo_root: Path to the repository root. Auto-detected if omitted.
        base: Git ref for incremental diff (default: HEAD~1).

    Returns:
        Summary with files_parsed/updated, node/edge counts, and errors.
    """
    store, root = _get_store(repo_root)
    try:
        if full_rebuild:
            result = full_build(root, store)
            return {
                "status": "ok",
                "build_type": "full",
                "summary": (
                    f"Full build complete: parsed {result['files_parsed']} files, "
                    f"created {result['total_nodes']} nodes and {result['total_edges']} edges."
                ),
                **result,
            }
        else:
            result = incremental_update(root, store, base=base)
            if result["files_updated"] == 0:
                return {
                    "status": "ok",
                    "build_type": "incremental",
                    "summary": "No changes detected. Graph is up to date.",
                    **result,
                }
            # #329: surface reviewer-oriented summary alongside raw counts.
            reviewer_summary = result.get("reviewer_summary") or {}
            summary_lines = [
                f"Incremental update: {result['files_updated']} files re-parsed, "
                f"{result['total_nodes']} nodes and {result['total_edges']} edges updated.",
                f"Changed: {result['changed_files']}. "
                f"Dependents also updated: {result['dependent_files']}.",
            ]
            if reviewer_summary:
                added = reviewer_summary.get("functions_added") or []
                removed = reviewer_summary.get("functions_removed") or []
                modified = reviewer_summary.get("functions_modified") or []
                impacted = reviewer_summary.get("modules_newly_impacted") or []
                summary_lines.append(
                    f"Reviewer summary: +{len(added)} / -{len(removed)} / "
                    f"~{len(modified)} functions, "
                    f"{len(impacted)} module(s) newly impacted."
                )
            return {
                "status": "ok",
                "build_type": "incremental",
                "summary": " ".join(summary_lines),
                **result,
            }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Graph build/update failed: {e}",
        }
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 2: get_impact_radius
# ---------------------------------------------------------------------------


_DEFAULT_IMPACT_PAYLOAD_BYTES = 500_000  # #315: ~500KB ceiling on impact JSON


def _estimate_payload_bytes(*payloads: list[dict] | dict) -> int:
    """Cheap upper-bound estimator for serialized JSON size.

    Avoids a full ``json.dumps`` round-trip on hot paths -- str(repr) is a
    reasonable proxy that overestimates moderately, which is the safe
    direction for a truncation gate.
    """
    return sum(len(repr(p)) for p in payloads)


def get_impact_radius(
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    max_results: int = 500,
    repo_root: str | None = None,
    base: str = "HEAD~1",
    max_payload_bytes: int = _DEFAULT_IMPACT_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Analyze the blast radius of changed files.

    Args:
        changed_files: Explicit list of changed file paths (relative to repo root).
                       If omitted, auto-detects from git diff.
        max_depth: How many hops to traverse in the graph (default: 2).
        max_results: Maximum number of impacted nodes to return (default: 500).
                     Maps to the BFS max_nodes parameter.
        repo_root: Repository root path. Auto-detected if omitted.
        base: Git ref for auto-detecting changes (default: HEAD~1).
        max_payload_bytes: Soft cap on serialized response size in bytes
            (default 500_000). When exceeded the impacted_nodes / edges
            arrays are truncated and ``results_truncated=True`` is set on
            the response with a hint suggesting ``max_depth=1`` or a
            narrower file scope. (#315.)

    Returns:
        Changed nodes, impacted nodes, impacted files, connecting edges,
        plus truncated flag and total_impacted count.
    """
    store, root = _get_store(repo_root)
    try:
        if changed_files is None:
            changed_files = get_changed_files(root, base)
            if not changed_files:
                changed_files = get_staged_and_unstaged(root)

        if not changed_files:
            return {
                "status": "ok",
                "summary": "No changed files detected.",
                "changed_nodes": [],
                "impacted_nodes": [],
                "impacted_files": [],
                "truncated": False,
                "total_impacted": 0,
            }

        # Convert to absolute paths for graph lookup
        abs_files = []
        root_resolved = root.resolve()
        for f in changed_files:
            full_path_raw = root / f
            full_path = full_path_raw.resolve()
            if not full_path.is_relative_to(root_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue
            abs_files.append(str(full_path))

        result = store.get_impact_radius(
            abs_files, max_depth=max_depth, max_nodes=max_results
        )

        changed_dicts = [node_to_dict(n) for n in result["changed_nodes"]]
        impacted_dicts = [node_to_dict(n) for n in result["impacted_nodes"]]
        edge_dicts = [edge_to_dict(e) for e in result["edges"]]
        truncated = result["truncated"]
        total_impacted = result["total_impacted"]

        summary_parts = [
            f"Blast radius for {len(changed_files)} changed file(s):",
            f"  - {len(changed_dicts)} nodes directly changed",
            f"  - {len(impacted_dicts)} nodes impacted (within {max_depth} hops)",
            f"  - {len(result['impacted_files'])} additional files affected",
        ]
        if truncated:
            summary_parts.append(
                f"  - TRUNCATED: results capped at {max_results} nodes"
                f" ({total_impacted} total impacted)"
            )

        # #315: payload-size auto-truncation. Even with max_results=500 the
        # impacted_nodes + edges arrays can blow past the conversation
        # token budget for shared utils (observed: 7.6MB, 12MB). Trim
        # iteratively until the rough JSON size fits under the soft cap.
        results_truncated = False
        results_truncated_reason: str | None = None
        original_impacted_count = len(impacted_dicts)
        original_edges_count = len(edge_dicts)
        if max_payload_bytes and max_payload_bytes > 0:
            estimated = _estimate_payload_bytes(
                changed_dicts, impacted_dicts, edge_dicts
            )
            if estimated > max_payload_bytes:
                results_truncated = True
                # Halve until we fit (or down to a minimum sample of 10 each).
                while _estimate_payload_bytes(
                    changed_dicts, impacted_dicts, edge_dicts
                ) > max_payload_bytes and (
                    len(impacted_dicts) > 10 or len(edge_dicts) > 10
                ):
                    impacted_dicts = impacted_dicts[: max(10, len(impacted_dicts) // 2)]
                    edge_dicts = edge_dicts[: max(10, len(edge_dicts) // 2)]
                results_truncated_reason = (
                    f"impact payload exceeded {max_payload_bytes} bytes "
                    f"(was approximately {estimated})"
                )
                summary_parts.append(
                    f"  - PAYLOAD TRUNCATED: kept {len(impacted_dicts)} of "
                    f"{original_impacted_count} impacted nodes / "
                    f"{len(edge_dicts)} of {original_edges_count} edges"
                )

        response: dict[str, Any] = {
            "status": "ok",
            "summary": "\n".join(summary_parts),
            "changed_files": changed_files,
            "changed_nodes": changed_dicts,
            "impacted_nodes": impacted_dicts,
            "impacted_files": result["impacted_files"],
            "edges": edge_dicts,
            "truncated": truncated,
            "total_impacted": total_impacted,
        }
        if results_truncated:
            response["results_truncated"] = True
            response["reason"] = results_truncated_reason
            response["hint"] = (
                "rerun with max_depth=1, narrow changed_files scope, or "
                "raise max_payload_bytes if you can handle a larger response"
            )
            response["original_impacted_count"] = original_impacted_count
            response["original_edges_count"] = original_edges_count
        return response
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 3: query_graph
# ---------------------------------------------------------------------------

_QUERY_PATTERNS = {
    "callers_of": "Find all functions that call a given function",
    "callees_of": "Find all functions called by a given function",
    "imports_of": "Find all imports of a given file or module",
    "importers_of": "Find all files that import a given file or module",
    "children_of": "Find all nodes contained in a file or class",
    "tests_for": "Find all tests for a given function or class",
    "inheritors_of": "Find all classes that inherit from a given class",
    "file_summary": "Get a summary of all nodes in a file",
}

# #318: cache of the last call-graph query response per repo_root so the
# spot_check action can fetch source snippets for N random callsites
# without re-running the query. Keyed by ``str(root.resolve())``.
_LAST_CALLERS_RESULT: dict[str, dict[str, Any]] = {}


def _list_kinds_in_graph(store: Any) -> list[str]:
    """Return distinct node kinds present in the graph (for D15 hints)."""
    try:
        rows = store._conn.execute(
            "SELECT DISTINCT kind FROM nodes ORDER BY kind"
        ).fetchall()
        return [r["kind"] for r in rows]
    except Exception:
        return []


def _resolve_query_target(
    store: Any,
    root: Any,
    target: str,
    pattern: str,
) -> tuple[Any | None, str, dict[str, Any] | None]:
    """Resolve the query target to a node or path.

    Returns:
        tuple: (node, resolved_qn_or_path, error_response)
    """
    original_target = target
    promoted_from_unqualified = False
    promoted_indexed_under: list[str] = []
    node = store.get_node(target)
    if not node:
        full_target_raw = root / target
        try:
            full_target = full_target_raw.resolve()
            if (
                full_target.is_relative_to(root.resolve())
                and not full_target_raw.is_symlink()
                and not full_target.is_symlink()
            ):
                abs_target = str(full_target)
                node = store.get_node(abs_target)
        except (OSError, ValueError):
            pass

    if not node:
        # Search by name
        candidates = store.search_nodes(target, limit=5)
        # #316: when the pattern is call-graph oriented and the only ambiguity
        # is between a File and a Function (common when a module name equals
        # a function name), the File target is meaningless -- callers_of /
        # callees_of want the Function. Auto-pick.
        if (
            len(candidates) > 1
            and pattern in ("callers_of", "callees_of")
            and "::" not in original_target
        ):
            functions = [c for c in candidates if c.kind == "Function"]
            files = [c for c in candidates if c.kind == "File"]
            non_call_kinds = [
                c for c in candidates if c.kind not in ("Function", "File")
            ]
            if len(functions) == 1 and len(files) >= 1 and not non_call_kinds:
                candidates = [functions[0]]
        if len(candidates) == 1:
            node = candidates[0]
            # Bare-name target was promoted to a qualified node; surface this
            # via the D15 advisory fields when the bare target differs from
            # the resolved qualified_name.
            if "::" not in original_target and "::" in node.qualified_name:
                promoted_from_unqualified = True
                promoted_indexed_under = [node.qualified_name]
            target = node.qualified_name
        elif len(candidates) > 1:
            # D15: distinguish ambiguous unqualified bare-name lookup from a
            # genuine "not_found". Keep status="ambiguous" for backward compat
            # but add reason="ambiguous_unqualified" + indexed_kinds + hint.
            return (
                None,
                target,
                {
                    "status": "ambiguous",
                    "reason": "ambiguous_unqualified",
                    "summary": (
                        f"Multiple matches for '{target}'. Please use a qualified name."
                    ),
                    "candidates": [node_to_dict(c) for c in candidates],
                    "indexed_kinds": sorted({c.kind for c in candidates}),
                    "indexed_under": [c.qualified_name for c in candidates],
                    "hint": (
                        f"Multiple symbols match '{target}'. "
                        "Try qualifying with namespace from indexed_under."
                    ),
                },
            )

    if not node:
        if pattern in ("file_summary", "importers_of"):
            full_target_raw = root / target
            try:
                full_target = full_target_raw.resolve()
                if (
                    not full_target.is_relative_to(root.resolve())
                    or full_target_raw.is_symlink()
                    or full_target.is_symlink()
                ):
                    return (
                        None,
                        target,
                        {
                            "status": "error",
                            "summary": "Invalid target path",
                        },
                    )
                return None, str(full_target), None
            except (OSError, ValueError):
                return (
                    None,
                    target,
                    {
                        "status": "error",
                        "summary": "Invalid target path",
                    },
                )
        else:
            # D15: bare not_found is ambiguous between three distinct failures.
            # Add reason field so callers can distinguish.
            indexed_kinds = _list_kinds_in_graph(store)
            return (
                None,
                target,
                {
                    "status": "not_found",
                    "reason": "no_such_symbol",
                    "summary": f"No node found matching '{target}'.",
                    "indexed_kinds": indexed_kinds,
                    "hint": (
                        f"Symbol '{target}' not indexed in graph. "
                        "Verify name spelling or pass a qualified form "
                        "('file_path::Class.method')."
                    ),
                },
            )

    if pattern == "importers_of" and node:
        return node, node.file_path, None

    if promoted_from_unqualified:
        # Stash advisory info on the store object as a simple side-channel.
        # query_graph() will read and propagate to the response.
        store._d15_promoted_indexed_under = promoted_indexed_under  # type: ignore[attr-defined]

    return node, node.qualified_name, None


# #331: dynamic-dispatch patterns the AST `CALLS` edge does not capture.
# When a `callers_of`/`callees_of` query targets a Function, scan the same-
# file references for these patterns so consumers know the AST answer is a
# lower bound, not exhaustive.
_DYNAMIC_DISPATCH_PATTERNS_PYTHON: tuple[tuple[str, str], ...] = (
    ("asyncio.to_thread", "asyncio.to_thread("),
    ("asyncio.ensure_future", "asyncio.ensure_future("),
    ("asyncio.create_task", "asyncio.create_task("),
    ("functools.partial", "functools.partial("),
    ("partial", "partial("),
    ("map", "map("),
    ("filter", "filter("),
    ("getattr-call", "getattr("),
)

_DYNAMIC_DISPATCH_PATTERNS_JS_TS: tuple[tuple[str, str], ...] = (
    (".bind", ".bind("),
    ("setTimeout", "setTimeout("),
    ("setInterval", "setInterval("),
)


def _scan_dynamic_dispatch_hints(
    store: Any,
    node: Any,
    target_name: str,
) -> list[dict[str, Any]]:
    """Scan files in the graph that mention the target name via known
    dynamic-dispatch patterns (#331).

    Best-effort textual scan of the same file as the target plus any file
    in the graph that imports it. Returns a list of ``{file, line,
    pattern, context}`` hits suitable for surfacing in the
    ``dynamic_dispatch_hints`` field of the ``callers_of`` response.
    """
    if node is None or not target_name:
        return []
    language = (getattr(node, "language", "") or "").lower()
    if language == "python":
        patterns = _DYNAMIC_DISPATCH_PATTERNS_PYTHON
    elif language in ("javascript", "typescript"):
        patterns = _DYNAMIC_DISPATCH_PATTERNS_JS_TS
    else:
        # Heuristic only implemented for Python + JS/TS today; other
        # languages return empty rather than guessing.
        return []

    target_file = node.file_path
    candidate_files: set[str] = {target_file}
    # Add same-package siblings that the graph already indexed as files that
    # import the target's file -- those are the most likely sites for
    # asyncio.to_thread(<target>) / functools.partial(<target>).
    try:
        for e in store.get_edges_by_target(target_file):  # type: ignore[attr-defined]
            if e.kind == "IMPORTS_FROM":
                candidate_files.add(e.file_path)
    except Exception:
        pass

    hits: list[dict[str, Any]] = []
    for fp in candidate_files:
        try:
            text = Path(fp).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if target_name not in line:
                continue
            for label, marker in patterns:
                if marker in line and target_name in line:
                    # Avoid trivially flagging the function's own def line.
                    stripped = line.lstrip()
                    if stripped.startswith(("def ", "async def ", "class ")):
                        continue
                    hits.append(
                        {
                            "file": fp,
                            "line": line_no,
                            "pattern": label,
                            "context": line.strip()[:160],
                        }
                    )
                    break  # one hit per line is enough
    return hits


def _handle_callers_of(
    store: Any, node: Any, qn: str, results: list[dict], edges_out: list[dict]
) -> None:
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind == "CALLS":
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))

    # Fallback: CALLS edges store unqualified target names
    if not qns and node:
        for e in store.search_edges_by_target_name(node.name):
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))

    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))


def _handle_callees_of(
    store: Any, qn: str, results: list[dict], edges_out: list[dict]
) -> None:
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CALLS":
            qns.append(e.target_qualified)
            edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))


def _handle_imports_of(
    store: Any, qn: str, results: list[dict], edges_out: list[dict]
) -> None:
    for e in store.get_edges_by_source(qn):
        if e.kind == "IMPORTS_FROM":
            results.append({"import_target": e.target_qualified})
            edges_out.append(edge_to_dict(e))


def _handle_importers_of(
    store: Any, abs_target: str, results: list[dict], edges_out: list[dict]
) -> None:
    for e in store.get_edges_by_target(abs_target):
        if e.kind == "IMPORTS_FROM":
            results.append({"importer": e.source_qualified, "file": e.file_path})
            edges_out.append(edge_to_dict(e))


def _handle_children_of(store: Any, qn: str, results: list[dict]) -> None:
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CONTAINS":
            qns.append(e.target_qualified)
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))


def _handle_tests_for(
    store: Any, node: Any, target: str, qn: str, results: list[dict]
) -> None:
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind == "TESTED_BY":
            qns.append(e.source_qualified)
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))
    # Also search by naming convention
    name = node.name if node else target
    test_nodes = store.search_nodes(f"test_{name}", limit=10)
    test_nodes += store.search_nodes(f"Test{name}", limit=10)
    seen = {r.get("qualified_name") for r in results}
    for t in test_nodes:
        if t.qualified_name not in seen and t.is_test:
            results.append(node_to_dict(t))


def _handle_inheritors_of(
    store: Any, qn: str, results: list[dict], edges_out: list[dict]
) -> None:
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind in ("INHERITS", "IMPLEMENTS"):
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))


def _handle_file_summary(store: Any, abs_path: str, results: list[dict]) -> None:
    file_nodes = store.get_nodes_by_file(abs_path)
    for n in file_nodes:
        results.append(node_to_dict(n))


# D16: allowed languages for the languages filter parameter.
# Mirrors the parser's supported language set (see CLAUDE.md "Supported languages").
_ALLOWED_LANGUAGES: set[str] = {
    "python",
    "typescript",
    "javascript",
    "go",
    "rust",
    "java",
    "csharp",
    "ruby",
    "kotlin",
    "swift",
    "php",
    "c",
    "cpp",
    "solidity",
}


def _validate_languages(languages: list[str] | None) -> dict[str, Any] | None:
    """Validate languages filter values; return error dict or None."""
    if languages is None:
        return None
    invalid = sorted(set(languages) - _ALLOWED_LANGUAGES)
    if invalid:
        return {
            "status": "error",
            "error": (
                f"invalid_languages: {invalid}; allowed: {sorted(_ALLOWED_LANGUAGES)}"
            ),
        }
    return None


def query_graph(
    pattern: str,
    target: str,
    repo_root: str | None = None,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Run a predefined graph query.

    Args:
        pattern: Query pattern. One of: callers_of, callees_of, imports_of,
                 importers_of, children_of, tests_for, inheritors_of, file_summary.
        target: The node name, qualified name, or file path to query about.
        repo_root: Repository root path. Auto-detected if omitted.
        languages: Optional list of language names to filter results to. Only
            applies to ``tests_for`` (filters returned test nodes by language).
            Allowed values: python, typescript, javascript, go, rust, java,
            csharp, ruby, kotlin, swift, php, c, cpp, solidity.

    Returns:
        Matching nodes and edges for the query.
    """
    if len(target) > 1000:
        return {
            "status": "error",
            "error": "Target too long (exceeds 1000 characters).",
        }

    lang_err = _validate_languages(languages)
    if lang_err:
        return lang_err

    store, root = _get_store(repo_root)
    try:
        if pattern not in _QUERY_PATTERNS:
            return {
                "status": "error",
                "error": f"Unknown pattern '{pattern}'. Available: {list(_QUERY_PATTERNS.keys())}",
            }

        results: list[dict] = []
        edges_out: list[dict] = []

        # For callers_of, skip common builtins early (bare names only)
        if (
            pattern == "callers_of"
            and target in _BUILTIN_CALL_NAMES
            and "::" not in target
        ):
            return {
                "status": "ok",
                "pattern": pattern,
                "target": target,
                "description": _QUERY_PATTERNS[pattern],
                "summary": f"'{target}' is a common builtin — callers_of skipped to avoid noise.",
                "results": [],
                "edges": [],
            }

        node, resolved_qn_or_path, error_resp = _resolve_query_target(
            store, root, target, pattern
        )
        if error_resp:
            return error_resp

        if pattern == "callers_of":
            _handle_callers_of(store, node, resolved_qn_or_path, results, edges_out)
        elif pattern == "callees_of":
            _handle_callees_of(store, resolved_qn_or_path, results, edges_out)
        elif pattern == "imports_of":
            _handle_imports_of(store, resolved_qn_or_path, results, edges_out)
        elif pattern == "importers_of":
            _handle_importers_of(store, resolved_qn_or_path, results, edges_out)
        elif pattern == "children_of":
            _handle_children_of(store, resolved_qn_or_path, results)
        elif pattern == "tests_for":
            _handle_tests_for(store, node, target, resolved_qn_or_path, results)
        elif pattern == "inheritors_of":
            _handle_inheritors_of(store, resolved_qn_or_path, results, edges_out)
        elif pattern == "file_summary":
            _handle_file_summary(store, resolved_qn_or_path, results)

        # D16: filter tests_for results by language if requested.
        if pattern == "tests_for" and languages is not None:
            results = [r for r in results if r.get("language") in languages]

        response: dict[str, Any] = {
            "status": "ok",
            "pattern": pattern,
            "target": target,
            "description": _QUERY_PATTERNS[pattern],
            "summary": f"Found {len(results)} result(s) for {pattern}('{target}')",
            "header": _build_response_header(store, get_db_path(root)),
            "results": results,
            "edges": edges_out,
        }

        # D15: surface bare-name -> qualified-name promotion (issue #339).
        promoted = getattr(store, "_d15_promoted_indexed_under", None)
        if promoted:
            response["resolved_from_unqualified"] = True
            response["indexed_under"] = list(promoted)
            response["hint"] = (
                f"Bare name '{target}' was auto-resolved to "
                f"{promoted[0]}. Pass the qualified form to disambiguate."
            )

        # #331: dynamic-dispatch blind-spot warning for callers_of /
        # callees_of. Surfaces same-file references via patterns
        # (asyncio.to_thread, functools.partial, decorator, etc.) that
        # the AST CALLS edge does not capture.
        if pattern in ("callers_of", "callees_of") and node is not None:
            hits = _scan_dynamic_dispatch_hints(store, node, node.name)
            if hits:
                response["dynamic_dispatch_hints"] = {
                    "target_file": node.file_path,
                    "same_file_references": hits[:50],
                    "note": (
                        "These are likely additional callers the AST "
                        "edge does not link. Grep before concluding the "
                        "caller list is complete."
                    ),
                }

        # #318: cache callsite-shaped results so `spot_check` can pull a
        # random sample of N source snippets without re-running the query.
        if pattern in (
            "callers_of",
            "callees_of",
            "inheritors_of",
            "importers_of",
        ):
            _LAST_CALLERS_RESULT[str(root.resolve())] = {
                "pattern": pattern,
                "target": target,
                "edges": list(edges_out),
                "results": list(results),
            }

        return response
    finally:
        store.close()


def spot_check_last_callers(
    n: int = 3,
    repo_root: str | None = None,
    context_lines: int = 2,
) -> dict[str, Any]:
    """Return source snippets for ``n`` random callsites from the last
    callers_of / callees_of / inheritors_of / importers_of result (#318).

    Lets a reviewer enforce per-query spot-check discipline (read one
    source line per graph result to confirm it wasn't a false positive)
    in 1 MCP call instead of N file Reads.

    Args:
        n: Number of random callsites to sample (default 3).
        repo_root: Repository root path. Auto-detected if omitted.
        context_lines: Lines of context to include before/after each
            callsite line (default 2).

    Returns:
        ``samples`` list of ``{file, line, snippet, source_qualified,
        target_qualified}`` plus the ``pattern`` and ``target`` of the
        cached query.
    """
    import random

    _, root = _get_store(repo_root)
    cached = _LAST_CALLERS_RESULT.get(str(root.resolve()))
    if not cached:
        return {
            "status": "no_cache",
            "summary": (
                "No prior callers_of/callees_of/inheritors_of/importers_of "
                "result cached for this repo. Run that query first."
            ),
            "samples": [],
        }

    edges = cached["edges"]
    if not edges:
        return {
            "status": "ok",
            "summary": "No edges in the last result to sample.",
            "pattern": cached["pattern"],
            "target": cached["target"],
            "samples": [],
        }

    sample_count = min(max(1, int(n)), len(edges))
    sampled = random.sample(edges, sample_count)
    samples: list[dict[str, Any]] = []
    for edge in sampled:
        file_path = edge.get("file_path") or ""
        line_no = int(edge.get("line") or 0)
        snippet = ""
        if file_path and line_no > 0:
            try:
                lines = (
                    Path(file_path)
                    .read_text(encoding="utf-8", errors="replace")
                    .splitlines()
                )
                start = max(0, line_no - 1 - context_lines)
                end = min(len(lines), line_no + context_lines)
                snippet = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
            except OSError:
                snippet = "(could not read file)"
        samples.append(
            {
                "file": file_path,
                "line": line_no,
                "snippet": snippet,
                "source_qualified": edge.get("source_qualified"),
                "target_qualified": edge.get("target_qualified"),
            }
        )

    return {
        "status": "ok",
        "summary": (
            f"Sampled {len(samples)} of {len(edges)} callsites from last "
            f"{cached['pattern']}('{cached['target']}')."
        ),
        "pattern": cached["pattern"],
        "target": cached["target"],
        "samples": samples,
    }


def renamed_in_diff(
    base: str = "HEAD~1",
    changed_files: list[str] | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Report symbols whose callsite line numbers shifted between ``base``
    and HEAD (#320).

    Reads each file at ``base`` via ``git show <base>:<file>``, parses it
    with the same tree-sitter pipeline as the live graph, and compares
    Function ``line_start`` per qualified name with the current file's
    symbols. Surfaces only symbols where the line shifted -- adds /
    removes are out of scope (the regular ``review`` flow already covers
    them). Useful for Stage 6 audits of large refactors where the question
    is "did this symbol genuinely move, or did the line just slide?".

    Args:
        base: Git ref to compare against (default ``HEAD~1``).
        changed_files: Files to check. Auto-detected from ``git diff base..HEAD``
            when omitted.
        repo_root: Repository root. Auto-detected if omitted.

    Returns:
        ``shifts`` list of ``{symbol, file, base_line, head_line, delta}``.
    """
    import subprocess

    from .parser import CodeParser

    store, root = _get_store(repo_root)
    try:
        if changed_files is None:
            changed_files = get_changed_files(root, base)
        if not changed_files:
            return {
                "status": "ok",
                "summary": "No changed files detected.",
                "base": base,
                "shifts": [],
            }

        parser = CodeParser()
        shifts: list[dict[str, Any]] = []
        repo_resolved = root.resolve()

        for rel_path in changed_files:
            full_path_raw = root / rel_path
            try:
                full_path = full_path_raw.resolve()
            except OSError:
                continue
            if not full_path.is_relative_to(repo_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue
            if not full_path.is_file():
                continue
            if parser.detect_language(full_path) is None:
                continue

            # Fetch base-ref content via git.
            try:
                proc = subprocess.run(
                    ["git", "show", f"{base}:{rel_path}"],
                    cwd=str(root),
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if proc.returncode != 0:
                # File didn't exist at base (added file) -- skip.
                continue
            base_source = proc.stdout
            if not base_source:
                continue

            try:
                base_nodes, _ = parser.parse_bytes(full_path, base_source)
                head_source = full_path.read_bytes()
                head_nodes, _ = parser.parse_bytes(full_path, head_source)
            except Exception:
                continue

            base_lines = {
                f"{n.parent_name}.{n.name}" if n.parent_name else n.name: n.line_start
                for n in base_nodes
                if n.kind == "Function" and n.line_start is not None
            }
            head_lines = {
                f"{n.parent_name}.{n.name}" if n.parent_name else n.name: n.line_start
                for n in head_nodes
                if n.kind == "Function" and n.line_start is not None
            }

            for symbol, base_line in base_lines.items():
                head_line = head_lines.get(symbol)
                if head_line is None:
                    continue  # removed -- out of scope for line-drift
                if head_line == base_line:
                    continue
                shifts.append(
                    {
                        "symbol": symbol,
                        "file": rel_path,
                        "base_line": base_line,
                        "head_line": head_line,
                        "delta": head_line - base_line,
                    }
                )

        return {
            "status": "ok",
            "summary": (
                f"Found {len(shifts)} symbol(s) whose callsite line shifted "
                f"between {base} and HEAD."
            ),
            "base": base,
            "shifts": shifts,
        }
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 4: get_review_context
# ---------------------------------------------------------------------------


def _filter_valid_paths(root: Path, changed_files: list[str]) -> list[str]:
    """Resolve and filter paths for safety and validity."""
    abs_files = []
    root_resolved = root.resolve()
    for f in changed_files:
        full_path_raw = root / f
        try:
            full_path = full_path_raw.resolve()
            if not full_path.is_relative_to(root_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue
            abs_files.append(str(full_path))
        except (OSError, ValueError):
            continue
    return abs_files


def _get_source_snippets(
    root: Path,
    changed_files: list[str],
    changed_nodes: list[Any],
    max_lines_per_file: int,
) -> dict[str, str]:
    """Generate source snippets for changed files."""
    snippets = {}
    root_resolved = root.resolve()
    for rel_path in changed_files:
        full_path_raw = root / rel_path
        try:
            full_path = full_path_raw.resolve()
            if not full_path.is_relative_to(root_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue
            if full_path.is_file():
                try:
                    lines = full_path.read_text(errors="replace").splitlines()
                    if len(lines) > max_lines_per_file:
                        snippets[rel_path] = _extract_relevant_lines(
                            lines, changed_nodes, str(full_path)
                        )
                    else:
                        snippets[rel_path] = "\n".join(
                            f"{i + 1}: {line}" for i, line in enumerate(lines)
                        )
                except (OSError, UnicodeDecodeError):
                    snippets[rel_path] = "(could not read file)"
        except (OSError, ValueError):
            continue
    return snippets


def _build_review_summary_text(
    changed_files_count: int,
    impact: dict[str, Any],
    guidance: str,
) -> str:
    """Construct the summary text for the review context."""
    summary_parts = [
        f"Review context for {changed_files_count} changed file(s):",
        f"  - {len(impact['changed_nodes'])} directly changed nodes",
        f"  - {len(impact['impacted_nodes'])} impacted nodes"
        f" in {len(impact['impacted_files'])} files",
        "",
        "Review guidance:",
        guidance,
    ]
    return "\n".join(summary_parts)


def _compute_untested_functions(
    impact: dict[str, Any],
    languages: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return changed Function nodes lacking TESTED_BY edges.

    D16: Optional ``languages`` filter scopes the list to functions whose
    ``language`` field matches one of the given values. Mitigates the
    cross-language false positive (issue #340) where Python implementations
    are flagged untested simply because tests live in JS/TS or in
    integration test fixtures.
    """
    tested_qns = set()
    for e in impact["edges"]:
        if e.kind == "TESTED_BY":
            tested_qns.add(e.source_qualified)
            tested_qns.add(e.target_qualified)

    out: list[dict[str, Any]] = []
    for n in impact["changed_nodes"]:
        if n.kind != "Function" or n.is_test:
            continue
        if n.qualified_name in tested_qns:
            continue
        if languages is not None and n.language not in languages:
            continue
        out.append(node_to_dict(n))
    return out


def get_review_context(
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    include_source: bool = True,
    max_lines_per_file: int = 200,
    repo_root: str | None = None,
    base: str = "HEAD~1",
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a focused review context from changed files.

    Builds a token-optimized subgraph + source snippets for code review.

    Args:
        changed_files: Files to review (auto-detected from git diff if omitted).
        max_depth: Impact radius depth (default: 2).
        include_source: Whether to include source code snippets (default: True).
        max_lines_per_file: Max source lines per file in output (default: 200).
        repo_root: Repository root path. Auto-detected if omitted.
        base: Git ref for change detection (default: HEAD~1).
        languages: Optional list of language names to scope the
            ``untested_functions`` field to. Functions whose ``language``
            isn't in the list are excluded. ``review_guidance`` text is
            re-derived from the filtered list. Allowed values: python,
            typescript, javascript, go, rust, java, csharp, ruby, kotlin,
            swift, php, c, cpp, solidity. (D16, fixes #340.)

    Returns:
        Structured review context with subgraph, source snippets, and review guidance.
    """
    lang_err = _validate_languages(languages)
    if lang_err:
        return lang_err

    store, root = _get_store(repo_root)
    try:
        if changed_files is None:
            changed_files = get_changed_files(root, base)
            if not changed_files:
                changed_files = get_staged_and_unstaged(root)

        if not changed_files:
            return {
                "status": "ok",
                "summary": "No changes detected. Nothing to review.",
                "context": {},
            }

        abs_files = _filter_valid_paths(root, changed_files)
        impact = store.get_impact_radius(abs_files, max_depth=max_depth)

        untested_functions = _compute_untested_functions(impact, languages=languages)

        context: dict[str, Any] = {
            "changed_files": changed_files,
            "impacted_files": impact["impacted_files"],
            "graph": {
                "changed_nodes": [node_to_dict(n) for n in impact["changed_nodes"]],
                "impacted_nodes": [node_to_dict(n) for n in impact["impacted_nodes"]],
                "edges": [edge_to_dict(e) for e in impact["edges"]],
            },
            "untested_functions": untested_functions,
        }
        if languages is not None:
            context["languages_filter"] = list(languages)

        if include_source:
            context["source_snippets"] = _get_source_snippets(
                root, changed_files, impact["changed_nodes"], max_lines_per_file
            )

        guidance = _generate_review_guidance(impact, changed_files, languages=languages)
        context["review_guidance"] = guidance

        return {
            "status": "ok",
            "summary": _build_review_summary_text(len(changed_files), impact, guidance),
            "context": context,
        }
    finally:
        store.close()


def _extract_relevant_lines(lines: list[str], nodes: list, file_path: str) -> str:
    """Extract only the lines relevant to changed nodes."""
    ranges = []
    for n in nodes:
        if n.file_path == file_path:
            start = max(0, n.line_start - 3)  # 2 lines context before
            end = min(len(lines), n.line_end + 2)  # 1 line context after
            ranges.append((start, end))

    if not ranges:
        # Show first N lines as fallback
        return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines[:50]))

    # Merge overlapping ranges
    ranges.sort()
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    parts: list[str] = []
    for start, end in merged:
        if parts:
            parts.append("...")
        for i in range(start, end):
            parts.append(f"{i + 1}: {lines[i]}")

    return "\n".join(parts)


def _generate_review_guidance(
    impact: dict,
    changed_files: list[str],
    languages: list[str] | None = None,
) -> str:
    """Generate review guidance based on the impact analysis.

    Args:
        impact: Impact-radius analysis output.
        changed_files: List of changed file paths (relative).
        languages: Optional language filter — when set, restrict the
            untested-function warning to functions whose ``language`` is
            in the list. (D16, fixes #340.)
    """
    guidance_parts = []

    # Check for test coverage
    tested_funcs = set()
    inheritance_edges_count = 0
    for e in impact["edges"]:
        if e.kind == "TESTED_BY":
            tested_funcs.add(e.source_qualified)
        elif e.kind in ("INHERITS", "IMPLEMENTS"):
            inheritance_edges_count += 1

    untested = []
    for n in impact["changed_nodes"]:
        if (
            n.kind == "Function"
            and not n.is_test
            and n.qualified_name not in tested_funcs
        ):
            if languages is None or n.language in languages:
                untested.append(n)

    if untested:
        guidance_parts.append(
            f"- {len(untested)} changed function(s) lack test coverage: "
            + ", ".join(n.name for n in untested[:5])
        )

    # Check for wide blast radius
    if len(impact["impacted_nodes"]) > 20:
        guidance_parts.append(
            f"- Wide blast radius: {len(impact['impacted_nodes'])} nodes impacted. "
            "Review callers and dependents carefully."
        )

    # Check for inheritance changes
    if inheritance_edges_count > 0:
        guidance_parts.append(
            f"- {inheritance_edges_count} inheritance/implementation relationship(s) affected. "
            "Check for Liskov substitution violations."
        )

    # Check for cross-file impact
    impacted_file_count = len(impact["impacted_files"])
    if impacted_file_count > 3:
        guidance_parts.append(
            f"- Changes impact {impacted_file_count} other files."
            " Consider splitting into smaller PRs."
        )

    if not guidance_parts:
        guidance_parts.append(
            "- Changes appear well-contained with minimal blast radius."
        )

    return "\n".join(guidance_parts)


# ---------------------------------------------------------------------------
# Tool 5: semantic_search_nodes
# ---------------------------------------------------------------------------


def _looks_like_literal_identifier(query: str) -> bool:
    """Heuristic for #317: would keyword-substring search on this query
    plausibly hit the user's intent?

    Single-token symbols (``foo``, ``foo_bar``, ``fooBar``,
    ``FooBar``, ``foo.bar``, ``foo::bar``) look like identifiers and are
    fine in keyword mode. Multi-word phrases, sentences, or queries with
    spaces / punctuation suggest semantic intent and warrant a warning
    when no embeddings are available.
    """
    q = query.strip()
    if not q:
        return True
    # Anything containing whitespace or sentence punctuation is treated as
    # a natural-language phrase (semantic intent).
    for ch in (" ", "\t", "\n", "?", "!", ","):
        if ch in q:
            return False
    # Lone allowed identifier characters: alnum, underscore, dot, hyphen,
    # slash, double-colon (qualified-name separator).
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-/:")
    return all(ch in allowed for ch in q)


def semantic_search_nodes(
    query: str,
    kind: str | None = None,
    limit: int = 20,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Search for nodes by name, keyword, or semantic similarity.

    Uses vector embeddings for semantic search if available (install with
    `pip install code-review-graph[embeddings]`). Falls back to keyword
    matching otherwise.

    Args:
        query: Search string to match against node names and qualified names.
        kind: Optional filter by node kind (File, Class, Function, Type, Test).
        limit: Maximum results to return (default: 20).
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Ranked list of matching nodes.
    """
    if len(query) > 1000:
        return {
            "status": "error",
            "error": "Query too long (exceeds 1000 characters).",
        }

    store, root = _get_store(repo_root)
    try:
        db_path = get_db_path(root)
        backend = init_backend()
        emb_store = EmbeddingStore(db_path, backend)
        search_mode = "keyword"

        try:
            if emb_store.available and emb_store.count() > 0:
                # Vector search
                search_mode = "semantic"
                raw = semantic_search(query, store, emb_store, limit=limit * 2)
                if kind:
                    raw = [r for r in raw if r.get("kind") == kind]
                raw = raw[:limit]
                return {
                    "status": "ok",
                    "query": query,
                    "search_mode": search_mode,
                    "summary": f"Found {len(raw)} node(s) matching '{query}' via semantic search"
                    + (f" (kind={kind})" if kind else ""),
                    "header": _build_response_header(
                        store, db_path, keyword_only=False
                    ),
                    "results": raw,
                }
        finally:
            emb_store.close()

        # Keyword fallback
        results = store.search_nodes(query, limit=limit * 2)

        if kind:
            results = [r for r in results if r.kind == kind]

        def score(node):
            name_lower = node.name.lower()
            q_lower = query.lower()
            if name_lower == q_lower:
                return 0
            if name_lower.startswith(q_lower):
                return 1
            return 2

        results.sort(key=score)
        results = results[:limit]

        response: dict[str, Any] = {
            "status": "ok",
            "query": query,
            "search_mode": search_mode,
            "summary": f"Found {len(results)} node(s) matching '{query}'"
            + (f" (kind={kind})" if kind else ""),
            "header": _build_response_header(store, db_path, keyword_only=True),
            "results": [node_to_dict(r) for r in results],
        }

        # #317: warn when running keyword fallback on a query that looks
        # semantic. Users who pass single identifiers (`foo`, `foo_bar`,
        # `Foo.bar`) are fine; users who pass phrases (`how does X work`,
        # `firebase auth setup`) get garbage from keyword-substring match.
        if not _looks_like_literal_identifier(query):
            response["warning"] = (
                "embeddings_count=0 - results are keyword-substring matches "
                "only, not semantic similarity. Query shape suggests semantic "
                "intent; rebuild with embeddings enabled "
                "(graph action=embed) or reword as a literal identifier."
            )
        return response
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 6: list_graph_stats
# ---------------------------------------------------------------------------


def list_graph_stats(repo_root: str | None = None) -> dict[str, Any]:
    """Get aggregate statistics about the knowledge graph.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Total nodes, edges, breakdown by kind, languages, and last update time.
    """
    store, root = _get_store(repo_root)
    try:
        stats = store.get_stats()

        summary_parts = [
            f"Graph statistics for {root.name}:",
            f"  Files: {stats.files_count}",
            f"  Total nodes: {stats.total_nodes}",
            f"  Total edges: {stats.total_edges}",
            f"  Languages: {', '.join(stats.languages) if stats.languages else 'none'}",
            f"  Last updated: {stats.last_updated or 'never'}",
            "",
            "Nodes by kind:",
        ]
        for kind, count in sorted(stats.nodes_by_kind.items()):
            summary_parts.append(f"  {kind}: {count}")
        summary_parts.append("")
        summary_parts.append("Edges by kind:")
        for kind, count in sorted(stats.edges_by_kind.items()):
            summary_parts.append(f"  {kind}: {count}")

        # Add embedding info if available
        backend = init_backend()
        emb_store = EmbeddingStore(get_db_path(root), backend)
        try:
            emb_count = emb_store.count()
            mode = resolve_backend()
            summary_parts.append("")
            summary_parts.append(
                f"Embeddings: {emb_count} nodes embedded (backend: {mode})"
            )
        finally:
            emb_store.close()

        return {
            "status": "ok",
            "summary": "\n".join(summary_parts),
            "total_nodes": stats.total_nodes,
            "total_edges": stats.total_edges,
            "nodes_by_kind": stats.nodes_by_kind,
            "edges_by_kind": stats.edges_by_kind,
            "languages": stats.languages,
            "files_count": stats.files_count,
            "last_updated": stats.last_updated,
            "embeddings_count": emb_count,
        }
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 7: embed_graph
# ---------------------------------------------------------------------------


def embed_graph(repo_root: str | None = None) -> dict[str, Any]:
    """Compute vector embeddings for all graph nodes to enable semantic search.

    Uses dual-mode embedding: local ONNX (qwen3-embed, default) or LiteLLM cloud.
    Fixed 768-dim storage via MRL truncation.

    Only embeds nodes that don't already have up-to-date embeddings.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Number of nodes embedded and total embedding count.
    """
    store, root = _get_store(repo_root)
    db_path = get_db_path(root)
    backend = init_backend()
    emb_store = EmbeddingStore(db_path, backend)
    try:
        mode = resolve_backend()
        newly_embedded = embed_all_nodes(store, emb_store)
        total = emb_store.count()

        return {
            "status": "ok",
            "summary": (
                f"Embedded {newly_embedded} new node(s) using {mode} backend. "
                f"Total embeddings: {total}. "
                "Semantic search is now active."
            ),
            "newly_embedded": newly_embedded,
            "total_embeddings": total,
            "backend": mode,
        }
    finally:
        emb_store.close()
        store.close()


# ---------------------------------------------------------------------------
# Tool 8: get_docs_section
# ---------------------------------------------------------------------------


def get_docs_section(section_name: str, repo_root: str | None = None) -> dict[str, Any]:
    """Return a specific section from the LLM-optimized reference.

    Used by skills and Claude Code to load only the exact documentation
    section needed, keeping token usage minimal (90%+ savings).

    Args:
        section_name: Exact section name. One of: usage, review-delta,
                      review-pr, commands, legal, watch, embeddings,
                      languages, troubleshooting.
        repo_root: Repository root path. Auto-detected from current directory if omitted.

    Returns:
        The section content, or an error if not found.
    """
    import re as _re

    search_roots: list[Path] = []

    if repo_root:
        search_roots.append(Path(repo_root))

    try:
        _, root = _get_store(repo_root)
        if root not in search_roots:
            search_roots.append(root)
    except (RuntimeError, ValueError):
        pass

    for search_root in search_roots:
        candidate = search_root / "docs" / "LLM-OPTIMIZED-REFERENCE.md"
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
            match = _re.search(
                rf'<section name="{_re.escape(section_name)}">'
                r"(.*?)</section>",
                content,
                _re.DOTALL | _re.IGNORECASE,
            )
            if match:
                return {
                    "status": "ok",
                    "section": section_name,
                    "content": match.group(1).strip(),
                }

    available = [
        "usage",
        "review-delta",
        "review-pr",
        "commands",
        "legal",
        "watch",
        "embeddings",
        "languages",
        "troubleshooting",
    ]
    return {
        "status": "not_found",
        "error": (
            f"Section '{section_name}' not found. Available: {', '.join(available)}"
        ),
    }


# ---------------------------------------------------------------------------
# Tool 9: find_large_functions
# ---------------------------------------------------------------------------


def find_large_functions(
    min_lines: int = 50,
    kind: str | None = None,
    file_path_pattern: str | None = None,
    limit: int = 50,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Find functions, classes, or files exceeding a line-count threshold.

    Useful for identifying decomposition targets, code-quality audits,
    and enforcing size limits during code review.

    Args:
        min_lines: Minimum line count to flag (default: 50).
        kind: Filter by node kind: Function, Class, File, or Test.
        file_path_pattern: Filter by file path substring (e.g. "components/").
        limit: Maximum results (default: 50).
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Oversized nodes with line counts, ordered largest first.
    """
    store, root = _get_store(repo_root)
    try:
        nodes = store.get_nodes_by_size(
            min_lines=min_lines,
            kind=kind,
            file_path_pattern=file_path_pattern,
            limit=limit,
        )

        results = []
        for n in nodes:
            d = node_to_dict(n)
            d["line_count"] = (
                (n.line_end - n.line_start + 1) if n.line_start and n.line_end else 0
            )
            # Make file_path relative for readability
            try:
                d["relative_path"] = str(Path(n.file_path).relative_to(root))
            except ValueError:
                d["relative_path"] = n.file_path
            results.append(d)

        summary_parts = [
            f"Found {len(results)} node(s) with >= {min_lines} lines"
            + (f" (kind={kind})" if kind else "")
            + (f" matching '{file_path_pattern}'" if file_path_pattern else "")
            + ":",
        ]
        for r in results[:10]:
            summary_parts.append(
                f"  {r['line_count']:>4} lines | {r['kind']:>8} | "
                f"{r['name']} ({r['relative_path']}:{r['line_start']})"
            )
        if len(results) > 10:
            summary_parts.append(f"  ... and {len(results) - 10} more")

        return {
            "status": "ok",
            "summary": "\n".join(summary_parts),
            "total_found": len(results),
            "min_lines": min_lines,
            "results": results,
        }
    finally:
        store.close()
