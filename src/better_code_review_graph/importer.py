"""Import a `crg`-format export back into a GraphStore (Task 6).

Pairs with :func:`better_code_review_graph.exporter.export_crg`: a graph
built and exported on one machine (e.g. a CI runner) can be merged into a
store on another (e.g. a laptop) without its ids colliding with whatever
that store already has, by namespacing every id with the exporting
``repo_id``.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from .parser import EdgeInfo, NodeInfo

if TYPE_CHECKING:
    from .federation import RepoRegistry
    from .graph import GraphStore

_SUPPORTED_SCHEMA_VERSION = 1


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
    no-op here regardless of whether ``registry``'s in-memory cache is stale.
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
    store._conn.commit()


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
    _register_repo_if_absent(store, registry, repo_id)

    nodes_added = 0
    nodes_updated = 0
    for node in payload["nodes"]:
        new_qualified_name = _namespace(node["qualified_name"], prefix)
        pre_existing = store.get_node(new_qualified_name) is not None

        node_id = store.upsert_node(
            NodeInfo(
                kind=node["kind"],
                name=node["name"],
                # _make_qualified() derives qualified_name from file_path, so
                # namespacing file_path here reproduces new_qualified_name
                # exactly (file_path is always a prefix of qualified_name).
                file_path=_namespace(node["file_path"], prefix),
                line_start=node["line_start"],
                line_end=node["line_end"],
                language=node["language"] or "",
                parent_name=node["parent_name"],
                params=node["params"],
                return_type=node["return_type"],
                modifiers=node["modifiers"],
                is_test=bool(node["is_test"]),
                extra=json.loads(node["extra"]) if node["extra"] else {},
                source_text=node["source_text"],
                repo_id=repo_id,
            ),
            file_hash=node["file_hash"] or "",
        )
        if pre_existing:
            nodes_updated += 1
        else:
            nodes_added += 1

        if node.get("summary") is not None:
            store.update_summary(
                node_id,
                summary=node["summary"],
                provider=node.get("summary_provider") or "",
                source_hash=node.get("source_hash") or "",
            )

    edges_added = 0
    for edge in payload["edges"]:
        new_source = _namespace(edge["source_qualified"], prefix)
        new_target = _namespace(edge["target_qualified"], prefix)
        # Mirrors GraphStore.upsert_edge's own natural-key match so we can
        # tell insert from update here -- upsert_edge only returns the row
        # id either way, and graph.py is out of scope for this task.
        pre_existing = (
            store._conn.execute(
                "SELECT 1 FROM edges WHERE kind=? AND source_qualified=? "
                "AND target_qualified=? AND file_path=? AND line=?",
                (edge["kind"], new_source, new_target, edge["file_path"], edge["line"]),
            ).fetchone()
            is not None
        )

        store.upsert_edge(
            EdgeInfo(
                kind=edge["kind"],
                source=new_source,
                target=new_target,
                file_path=edge["file_path"],
                line=edge["line"],
                extra=json.loads(edge["extra"]) if edge["extra"] else {},
                repo_id=repo_id,
            )
        )
        if not pre_existing:
            edges_added += 1

    store.commit()
    store._invalidate_cache()

    return {
        "nodes_added": nodes_added,
        "nodes_updated": nodes_updated,
        "edges_added": edges_added,
        "repo_id": repo_id,
    }
