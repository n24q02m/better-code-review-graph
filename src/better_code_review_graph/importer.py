"""Import a `crg`-format export back into a GraphStore (Task 6).

Pairs with :func:`better_code_review_graph.exporter.export_crg`: a graph
built and exported on one machine (e.g. a CI runner) can be merged into a
store on another (e.g. a laptop) without its ids colliding with whatever
that store already has, by namespacing every id with the exporting
``repo_id``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .federation import RepoRegistry
    from .graph import GraphStore

_SUPPORTED_SCHEMA_VERSION = 1
_ZERO_SHA = "0" * 40


def _namespace(value: str, prefix: str) -> str:
    """Prefix ``value`` with ``prefix`` unless it is already prefixed.

    The "already prefixed" guard keeps re-importing an already-namespaced
    payload (e.g. re-exporting an import result) from stacking prefixes.
    """
    return value if value.startswith(prefix) else f"{prefix}{value}"


def _register_repo_if_absent(
    store: GraphStore, registry: RepoRegistry, repo_id: str
) -> None:
    """Record the imported repo as a known participant for repo-scoped queries.

    ``RepoRegistry.add`` always re-derives the id from a filesystem path, so
    it cannot be told to keep the exact incoming ``repo_id`` -- an import has
    no meaningful local path to derive from in the first place. This writes
    the ``repos`` row directly (same shape ``RepoRegistry`` itself reads),
    guarded by ``INSERT OR IGNORE`` so re-importing the same payload is a
    no-op here regardless of whether ``registry``'s in-memory cache is
    stale. Left uncommitted -- ``import_graph`` commits everything together.
    """
    if repo_id in {entry.repo_id for entry in registry.entries()}:
        return
    now = int(time.time())
    store._conn.execute(
        "INSERT OR IGNORE INTO repos "
        "(repo_id, path, remote_url, last_indexed_sha, first_indexed_at, last_indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (repo_id, f"<imported:{repo_id}>", None, None, now, now),
    )


def _upsert_imported_node(
    store: GraphStore, qualified_name: str, node: dict[str, Any], repo_id: str
) -> bool:
    """Insert/update a ``nodes`` row with an explicit, already-namespaced id.

    ``GraphStore.upsert_node`` always derives ``qualified_name`` from
    ``file_path`` via ``_make_qualified`` -- it has no way to accept an
    explicit qualified_name, so the only way to produce a namespaced id
    through it is to namespace ``file_path`` itself. That corrupts
    ``file_path`` into a non-path (`get_nodes_by_file` can no longer find
    the node by its real path, and it stops matching the corresponding
    edges' un-namespaced ``file_path``). This mirrors ``upsert_node``'s own
    ``INSERT ... ON CONFLICT(qualified_name) DO UPDATE`` shape (graph.py is
    out of scope for this task) but takes ``qualified_name`` and the
    temporal columns explicitly, leaving ``file_path`` as the real source
    path -- matching how federated multi-root builds already disambiguate
    files (via the separate ``repo_id`` column + naturally-distinct
    filesystem paths), not by mangling ``file_path``.

    ``summary``/``summary_provider``/``source_hash`` are folded into the
    same statement rather than calling ``GraphStore.update_summary``
    afterward -- that method does its own ``commit()``, which would end
    the transaction ``import_graph`` wraps the whole merge in, making a
    partial-import rollback silently not roll back whenever a node carries
    a summary. The ``COALESCE(excluded.x, x)`` pattern keeps a locally
    generated summary intact when the imported payload doesn't carry one
    (e.g. the source repo was never summarized) instead of clobbering it
    with NULL on every re-import -- the same behavior the previous
    ``if node.get("summary") is not None`` guard produced.

    Returns ``True`` if ``qualified_name`` already existed (row updated),
    ``False`` if it was newly inserted.
    """
    now = time.time()
    pre_existing = (
        store._conn.execute(
            "SELECT 1 FROM nodes WHERE qualified_name = ?", (qualified_name,)
        ).fetchone()
        is not None
    )
    store._conn.execute(
        """INSERT INTO nodes
           (kind, name, qualified_name, file_path, line_start, line_end,
            language, parent_name, params, return_type, modifiers, is_test,
            file_hash, extra, updated_at, source_text, repo_id,
            valid_from_sha, valid_to_sha, summary, summary_provider, source_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(qualified_name) DO UPDATE SET
             kind=excluded.kind, name=excluded.name,
             file_path=excluded.file_path, line_start=excluded.line_start,
             line_end=excluded.line_end, language=excluded.language,
             parent_name=excluded.parent_name, params=excluded.params,
             return_type=excluded.return_type, modifiers=excluded.modifiers,
             is_test=excluded.is_test, file_hash=excluded.file_hash,
             extra=excluded.extra, updated_at=excluded.updated_at,
             source_text=excluded.source_text, repo_id=excluded.repo_id,
             valid_from_sha=excluded.valid_from_sha,
             valid_to_sha=excluded.valid_to_sha,
             summary=COALESCE(excluded.summary, summary),
             summary_provider=COALESCE(excluded.summary_provider, summary_provider),
             source_hash=COALESCE(excluded.source_hash, source_hash)
        """,
        (
            node["kind"],
            node["name"],
            qualified_name,
            node["file_path"],
            node["line_start"],
            node["line_end"],
            node["language"] or "",
            node["parent_name"],
            node["params"],
            node["return_type"],
            node["modifiers"],
            node["is_test"],
            node["file_hash"] or "",
            node["extra"] if node["extra"] else "{}",
            now,
            node["source_text"],
            repo_id,
            node.get("valid_from_sha") or _ZERO_SHA,
            node.get("valid_to_sha"),
            node.get("summary"),
            node.get("summary_provider"),
            node.get("source_hash"),
        ),
    )
    return pre_existing


def _upsert_imported_edge(
    store: GraphStore,
    new_source: str,
    new_target: str,
    edge: dict[str, Any],
    repo_id: str,
) -> bool:
    """Insert/update an ``edges`` row, carrying the temporal columns through.

    Mirrors ``GraphStore.upsert_edge``'s natural-key match (kind + source +
    target + file_path + line) and insert/update shape, extended with the
    ``valid_from_sha``/``valid_to_sha`` columns ``upsert_edge`` doesn't set
    (same graph.py-out-of-scope reasoning as :func:`_upsert_imported_node`).
    ``edge["file_path"]`` is passed through untouched -- consistent with
    leaving node ``file_path`` real (see :func:`_upsert_imported_node`).

    Returns ``True`` if a new row was inserted, ``False`` if an existing
    one was updated.
    """
    now = time.time()
    extra_str = edge["extra"] if edge["extra"] else "{}"
    valid_from_sha = edge.get("valid_from_sha") or _ZERO_SHA
    valid_to_sha = edge.get("valid_to_sha")

    existing = store._conn.execute(
        "SELECT id FROM edges WHERE kind=? AND source_qualified=? "
        "AND target_qualified=? AND file_path=? AND line=?",
        (edge["kind"], new_source, new_target, edge["file_path"], edge["line"]),
    ).fetchone()

    if existing:
        store._conn.execute(
            "UPDATE edges SET extra=?, updated_at=?, repo_id=?, "
            "valid_from_sha=?, valid_to_sha=? WHERE id=?",
            (extra_str, now, repo_id, valid_from_sha, valid_to_sha, existing["id"]),
        )
        return False

    store._conn.execute(
        """INSERT INTO edges
           (kind, source_qualified, target_qualified, file_path, line,
            extra, updated_at, repo_id, valid_from_sha, valid_to_sha)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            edge["kind"],
            new_source,
            new_target,
            edge["file_path"],
            edge["line"],
            extra_str,
            now,
            repo_id,
            valid_from_sha,
            valid_to_sha,
        ),
    )
    return True


def import_graph(
    store: GraphStore, registry: RepoRegistry, payload: dict[str, Any]
) -> dict[str, Any]:
    """Merge a ``crg``-format payload into ``store``.

    Args:
        store: Target graph store to write into.
        registry: Registry bound to the same ``store``, used to record the
            imported repo as a known participant (see
            :func:`_register_repo_if_absent`).
        payload: Parsed JSON produced by
            :func:`better_code_review_graph.exporter.export_crg`.

    Returns:
        Dict with ``nodes_added``, ``nodes_updated``, ``edges_added``, and
        ``repo_id``.

    Raises:
        ValueError: If ``payload["schema_version"]`` is not the version this
            importer understands.
    """
    schema_version = payload.get("schema_version")
    if schema_version != _SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported crg schema_version {schema_version!r}; "
            f"this importer only understands schema_version={_SUPPORTED_SCHEMA_VERSION}."
        )

    repo_id = payload["repo_id"]
    prefix = f"{repo_id}::"

    # Single transaction for the whole merge: a failure partway through
    # (e.g. a malformed node dict) rolls back rather than leaving a
    # partially-imported graph committed. (Summary columns are written by
    # _upsert_imported_node itself rather than a separate
    # store.update_summary() call, since that method commits on its own
    # and would end this transaction early.)
    with store._conn:
        _register_repo_if_absent(store, registry, repo_id)

        nodes_added = 0
        nodes_updated = 0
        for node in payload["nodes"]:
            new_qualified_name = _namespace(node["qualified_name"], prefix)
            pre_existing = _upsert_imported_node(
                store, new_qualified_name, node, repo_id
            )
            if pre_existing:
                nodes_updated += 1
            else:
                nodes_added += 1

        edges_added = 0
        for edge in payload["edges"]:
            new_source = _namespace(edge["source_qualified"], prefix)
            new_target = _namespace(edge["target_qualified"], prefix)
            if _upsert_imported_edge(store, new_source, new_target, edge, repo_id):
                edges_added += 1

    store._invalidate_cache()

    return {
        "nodes_added": nodes_added,
        "nodes_updated": nodes_updated,
        "edges_added": edges_added,
        "repo_id": repo_id,
    }
