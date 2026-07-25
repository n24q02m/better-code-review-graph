"""Shared read-only helpers for the plugin hooks.

The hooks run on the interactive path -- before every prompt and after every
shell call -- so everything here is cheap, dependency-free, and read-only:
no package import, no graph build, no writes. Every helper returns ``None``
rather than raising when it cannot answer, because a hook that fails must
degrade to silence instead of interrupting the session.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

GRAPH_DIR = ".code-review-graph"
GRAPH_DB = "graph.db"
PREFIX = "[better-code-review-graph]"


def find_repo_root(start: Path) -> Path | None:
    """Walk upward for the nearest directory holding a graph or a git dir."""
    try:
        candidates = (start, *start.parents)
    except OSError:
        return None
    for candidate in candidates:
        if (candidate / GRAPH_DIR / GRAPH_DB).is_file():
            return candidate
        if (candidate / ".git").exists():
            return candidate
    return None


def graph_db_path(repo_root: Path) -> Path:
    return repo_root / GRAPH_DIR / GRAPH_DB


def git_dir(repo_root: Path) -> Path | None:
    """Resolve the git directory, following a worktree pointer file."""
    git_path = repo_root / ".git"
    if git_path.is_dir():
        return git_path
    if not git_path.is_file():
        return None
    text = git_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text.startswith("gitdir:"):
        return None
    target = Path(text.split(":", 1)[1].strip())
    if not target.is_absolute():
        target = (repo_root / target).resolve()
    return target if target.is_dir() else None


def _resolve_ref(gdir: Path, ref: str) -> str | None:
    """Resolve a ref through loose files, then packed-refs, then commondir."""
    loose = gdir / ref
    if loose.is_file():
        return loose.read_text(encoding="utf-8", errors="replace").strip() or None

    packed = gdir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(("#", "^")) or not line.strip():
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]

    # Linked worktrees keep HEAD locally but share refs with the main git dir.
    commondir = gdir / "commondir"
    if commondir.is_file():
        rel = commondir.read_text(encoding="utf-8", errors="replace").strip()
        if rel:
            common = Path(rel)
            if not common.is_absolute():
                common = (gdir / common).resolve()
            if common.is_dir() and common != gdir:
                return _resolve_ref(common, ref)
    return None


def read_head(gdir: Path) -> str | None:
    """Return the commit HEAD points at, without spawning git."""
    head_file = gdir / "HEAD"
    if not head_file.is_file():
        return None
    head = head_file.read_text(encoding="utf-8", errors="replace").strip()
    if not head:
        return None
    if not head.startswith("ref:"):
        return head
    return _resolve_ref(gdir, head.split(":", 1)[1].strip())


def read_metadata(db_path: Path, key: str) -> str | None:
    """Read one key from the graph metadata table, read-only."""
    if not db_path.is_file():
        return None
    uri = f"file:{db_path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=0.5)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return row[0] if row else None
