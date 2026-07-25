"""UserPromptSubmit hook: warn when the knowledge graph has fallen behind.

Emits a single advisory line so the assistant refreshes the graph before
trusting its answers. It warns, it never blocks: every path exits 0, and any
unexpected failure exits 0 silently. A hook that interrupts a prompt is worse
than no hook at all.

Two independent staleness signals, either of which triggers the advisory:

* HEAD drift -- the commit recorded at the last build is no longer the
  checked-out commit, so the graph describes code other than the working tree.
* Age -- the graph has not been rewritten for ``CRG_STALE_HOURS`` hours
  (default 24). Set ``CRG_STALE_HOURS=0`` to disable the age signal and warn
  on HEAD drift only.

Nothing is printed when no graph exists; the SessionStart hook already covers
that case, and repeating it on every prompt would be noise.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from _graph_state import (
    PREFIX,
    find_repo_root,
    git_dir,
    graph_db_path,
    read_head,
    read_metadata,
)

DEFAULT_STALE_HOURS = 24.0


def stale_hours() -> float:
    raw = os.environ.get("CRG_STALE_HOURS", "").strip()
    if not raw:
        return DEFAULT_STALE_HOURS
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_STALE_HOURS


def main() -> int:
    repo_root = find_repo_root(Path.cwd())
    if repo_root is None:
        return 0

    db_path = graph_db_path(repo_root)
    if not db_path.is_file():
        return 0

    reasons: list[str] = []

    gdir = git_dir(repo_root)
    head = read_head(gdir) if gdir is not None else None
    last_built = read_metadata(db_path, "last_built_head")
    if head and last_built and head != last_built:
        reasons.append(
            f"HEAD is {head[:8]} but the graph was built at {last_built[:8]}"
        )

    threshold = stale_hours()
    if threshold > 0:
        try:
            age_hours = (time.time() - db_path.stat().st_mtime) / 3600.0
        except OSError:
            age_hours = 0.0
        if age_hours > threshold:
            reasons.append(
                f"last indexed {age_hours:.0f}h ago (threshold {threshold:.0f}h)"
            )

    if not reasons:
        return 0

    print(
        f"{PREFIX} Knowledge graph may be stale: {'; '.join(reasons)}. "
        'Run graph(action="update") before relying on graph queries -- or make '
        "any edit, which lets the incremental hook refresh it."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # A hook must never break the prompt it is attached to.
        sys.exit(0)
