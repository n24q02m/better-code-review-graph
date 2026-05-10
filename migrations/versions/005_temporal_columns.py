"""Temporal columns: BREAKING add valid_from_sha / valid_to_sha (Phase 3 Task 6).

Revision ``005`` is the v2.0.0 BREAKING migration that introduces
SHA-anchored temporal tracking on every graph row. The new columns let
the v2 query layer answer "what did the graph look like at commit X?"
without re-running the parser by intersecting ``valid_from_sha`` (the
commit the row first appeared at) with ``valid_to_sha`` (the commit that
superseded it; ``NULL`` means the row is still current).

Schema additions (both ``nodes`` and ``edges``):

* ``valid_from_sha`` (TEXT, NOT NULL, ``server_default = <repo-HEAD-SHA-at-migration-time>``)
  — backfills every pre-existing row with the current repo HEAD so the
  temporal lineage starts cleanly. New ``INSERT`` statements that omit
  this column inherit the same DDL default; the v2 ingest path is
  expected to set the column explicitly per-commit so the default only
  matters for forensic / migration-day rows.
* ``valid_to_sha`` (TEXT, NULL allowed, no default) — ``NULL`` is the
  semantic sentinel for "currently valid". The v2 supersede path will
  ``UPDATE ... SET valid_to_sha = <new-commit>`` rather than deleting
  rows, preserving history.
* ``idx_nodes_temporal`` on ``nodes(valid_from_sha, valid_to_sha)`` and
  ``idx_edges_temporal`` on ``edges(valid_from_sha, valid_to_sha)`` —
  the canonical scan pattern for "as-of <sha>" lookups.

BREAKING — why
--------------
Previous additive migrations (003 federation, 004 security_tags) used
``server_default = ''`` or ``NULL`` so existing rows backfilled
trivially. ``valid_from_sha NOT NULL`` cannot use an empty default
(querying ``WHERE valid_from_sha = ''`` would mean "rows from no
commit" — semantically undefined). We therefore have to read the actual
repo HEAD at migration time and bake it into the DDL default. That step
requires a working git repo on disk; if absent, the migration aborts
with an actionable :class:`RuntimeError` (the operator can either point
the DB at a repo or set ``CRG_DOWNGRADE_TO_1_X=1`` to restore the
pre-2.0 backup taken by the Phase 3 Task 1 hook).

Repo discovery
--------------
The migration extracts the SQLite file path from the alembic
``sqlalchemy.url`` and walks up its parent chain looking for a
``.git`` entry (file or directory — supports submodules / worktrees).
The walk-up matches ``crg``'s storage convention of placing
``graph.db`` at ``<repo>/.code-review-graph/graph.db`` but does not
hard-code the depth: any ancestor with ``.git`` qualifies.

SQLite limitations
------------------
SQLite < 3.35 cannot ``ALTER TABLE DROP COLUMN`` natively. The
downgrade path therefore wraps each table in ``op.batch_alter_table``
which performs the create-new-table-copy-drop-old-rename dance under
the hood. Indexes are dropped first (in the same direction the upgrade
created them) so the downgrade does not leave orphaned index entries
referring to dropped columns.

Revision ID: 005
Revises: 004
Create Date: 2026-05-10
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Recognized SQLite URL shapes that ``GraphStore`` and the test helpers
# build via ``Config.set_main_option("sqlalchemy.url", ...)``. The
# SQLAlchemy convention is always exactly 3 slashes after ``sqlite:``:
#
# * ``sqlite:///C:/path/g.db`` — Windows absolute (path = ``C:/path/g.db``)
# * ``sqlite:////tmp/g.db`` — POSIX absolute (path = ``/tmp/g.db``; the
#   4th slash is the leading slash of the absolute path, NOT part of
#   the prefix)
# * ``sqlite:///rel/path/g.db`` — relative (path = ``rel/path/g.db``)
#
# A previous version of this regex used ``{2,4}`` for the slash count,
# which is greedy and silently swallowed the leading ``/`` on POSIX
# absolute URLs (turning ``sqlite:////tmp/g.db`` into the relative
# path ``tmp/g.db``). On Linux/macOS CI runners that resolved against
# the pytest CWD (= project workspace), so the walk-up in
# :func:`_find_repo_root` ended at the project's ``.git`` instead of
# the test fixture's tmp_path ``.git``. Pinning to exactly 3 slashes
# preserves the leading slash on POSIX absolute paths.
_SQLITE_URL_RE = re.compile(r"^sqlite:///(?P<path>.+)$")

# Sentinel SHA used when the migration cannot read a real HEAD:
# 40 zeros is git's empty-tree marker and stable across hosts. The
# migration uses this sentinel for two distinct cases:
#
# 1. ``:memory:`` URLs — those DBs do not survive the process so the
#    SHA we bake into the DDL default is only the value for transient
#    test rows. There is nothing to back-fill on disk.
#
# 2. ``CRG_TEST_ALLOW_NO_GIT=1`` is set in the environment AND no
#    ``.git`` ancestor is reachable from the DB path. This is the
#    test-suite escape hatch: pytest creates throwaway DBs in
#    ``tmp_path`` / ``tempfile.NamedTemporaryFile`` paths that live
#    outside any git repo, and several legacy tests deliberately
#    probe behaviour that assumes those tmp dirs are NOT inside a
#    git repo. Without the escape hatch every test would have to
#    git-init its own tmp dir, which conflicts with tests that
#    construct ``tmp_path / ".git"`` themselves.
#
# Production code paths leave ``CRG_TEST_ALLOW_NO_GIT`` unset, so the
# migration still aborts with the actionable :class:`RuntimeError`
# whenever a file-backed DB has no reachable repo — production data
# stays correctly tagged.
_IN_MEMORY_SENTINEL_SHA: str = "0" * 40
_TEST_ALLOW_NO_GIT_ENV_VAR: str = "CRG_TEST_ALLOW_NO_GIT"


def _extract_db_path_from_url(url: str) -> Path | None:
    """Return the on-disk SQLite file path encoded in ``url``.

    Returns ``None`` for ``:memory:`` URLs — the caller treats that as
    "skip the git lookup and use the in-memory sentinel SHA". Raises
    :class:`RuntimeError` for any URL that does not match the
    documented file-backed shape.
    """
    if "memory" in url.lower():
        return None
    match = _SQLITE_URL_RE.match(url)
    if match is None:
        raise RuntimeError(
            f"005_temporal_columns received an unrecognized SQLAlchemy URL "
            f"({url!r}); expected a sqlite:/// file URL."
        )
    raw = match.group("path")
    # The exactly-3-slash regex preserves the leading slash on POSIX
    # absolute paths: ``sqlite:////tmp/g.db`` → ``raw = '/tmp/g.db'``.
    # Windows absolute URLs use the same 3-slash prefix and yield e.g.
    # ``raw = 'C:/path/g.db'``. Relative paths (``sqlite:///rel/path``)
    # are not used in production but still resolve against the cwd so
    # the walk-up below works for any caller that constructs them.
    return Path(raw).resolve()


def _find_repo_root(db_path: Path) -> Path:
    """Walk parents of ``db_path`` looking for a ``.git`` entry.

    Both directories (regular clones) and files (submodules and git
    worktrees use a ``.git`` text file pointing at the real gitdir)
    qualify. Returns the first ancestor that contains either.

    Raises :class:`RuntimeError` with the actionable message if the
    walk reaches the filesystem root without finding ``.git``.
    """
    for ancestor in db_path.parents:
        candidate = ancestor / ".git"
        if candidate.exists():
            return ancestor
    raise RuntimeError(
        "005_temporal_columns requires git in repo containing the graph "
        f"DB. The migration backfills valid_from_sha with the current "
        f"HEAD commit. No .git found walking up from {db_path}. To skip "
        "migration, set CRG_DOWNGRADE_TO_1_X=1 to restore the pre-2.0 "
        "backup."
    )


def _read_head_sha(repo_root: Path) -> str:
    """Run ``git rev-parse HEAD`` in ``repo_root`` and return the SHA.

    Raises :class:`RuntimeError` with the actionable message on any
    git failure (binary missing, repo corrupt, no commits yet). The
    error spells out the same downgrade escape hatch as the no-git
    branch so operators see one consistent recovery path.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        raise RuntimeError(
            "005_temporal_columns requires git in repo containing the graph "
            "DB. The migration backfills valid_from_sha with the current "
            f"HEAD commit. `git rev-parse HEAD` failed in {repo_root}: "
            f"{exc}. To skip migration, set CRG_DOWNGRADE_TO_1_X=1 to "
            "restore the pre-2.0 backup."
        ) from exc
    sha = result.stdout.strip()
    if not sha:
        raise RuntimeError(
            "005_temporal_columns requires git in repo containing the graph "
            "DB. The migration backfills valid_from_sha with the current "
            f"HEAD commit. `git rev-parse HEAD` returned empty output in "
            f"{repo_root}. To skip migration, set CRG_DOWNGRADE_TO_1_X=1 "
            "to restore the pre-2.0 backup."
        )
    return sha


def _resolve_head_sha() -> str:
    """End-to-end HEAD resolution: URL -> db path -> repo root -> SHA.

    Returns the in-memory sentinel SHA (40 zeros) when:

    * the DB URL points at ``:memory:`` — those DBs don't survive the
      process so the value is only the DDL default for transient tests, OR
    * the file-backed DB has no reachable ``.git`` ancestor AND the
      operator has opted in to the test-only escape hatch via
      ``CRG_TEST_ALLOW_NO_GIT=1``.

    File-backed DBs without a reachable ``.git`` ancestor and without
    the test escape hatch still raise the actionable
    :class:`RuntimeError` so production data isn't silently mis-tagged.
    """
    url = op.get_context().config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "005_temporal_columns could not read sqlalchemy.url from the "
            "alembic context. The migration requires a file-backed DB to "
            "locate the enclosing git repo."
        )
    db_path = _extract_db_path_from_url(url)
    if db_path is None:
        return _IN_MEMORY_SENTINEL_SHA
    try:
        repo_root = _find_repo_root(db_path)
        return _read_head_sha(repo_root)
    except RuntimeError:
        # Test-only escape hatch — see module docstring on
        # ``_TEST_ALLOW_NO_GIT_ENV_VAR``. Re-raise in production.
        # Both ``_find_repo_root`` (no .git ancestor) and
        # ``_read_head_sha`` (placeholder ``.git`` directory created by
        # tests that mock the marker without ``git init``) raise the
        # same actionable RuntimeError; the env-var fallback covers
        # both so legacy fixtures that create a bare ``.git`` directory
        # don't have to also seed a real commit.
        if os.environ.get(_TEST_ALLOW_NO_GIT_ENV_VAR) == "1":
            return _IN_MEMORY_SENTINEL_SHA
        raise


def upgrade() -> None:
    """Add temporal columns + indexes, backfilled with the repo HEAD SHA."""
    head_sha = _resolve_head_sha()

    # NOT NULL with the HEAD SHA as the DDL default — this single SQL
    # statement both backfills every existing row and sets the default
    # for any future INSERT that omits the column. The v2 ingest path
    # is expected to write the column explicitly per-commit; the
    # default only matters for migration-day rows + tests.
    op.add_column(
        "nodes",
        sa.Column(
            "valid_from_sha",
            sa.Text(),
            nullable=False,
            server_default=sa.text(f"'{head_sha}'"),
        ),
    )
    op.add_column(
        "nodes",
        sa.Column("valid_to_sha", sa.Text(), nullable=True),
    )
    op.add_column(
        "edges",
        sa.Column(
            "valid_from_sha",
            sa.Text(),
            nullable=False,
            server_default=sa.text(f"'{head_sha}'"),
        ),
    )
    op.add_column(
        "edges",
        sa.Column("valid_to_sha", sa.Text(), nullable=True),
    )

    # Composite indexes — the canonical "as-of <sha>" scan pattern.
    op.create_index("idx_nodes_temporal", "nodes", ["valid_from_sha", "valid_to_sha"])
    op.create_index("idx_edges_temporal", "edges", ["valid_from_sha", "valid_to_sha"])


def downgrade() -> None:
    """Drop temporal indexes + columns.

    Indexes are dropped before the columns they reference. SQLite < 3.35
    lacks native ``ALTER TABLE DROP COLUMN`` so each column drop is
    wrapped in ``op.batch_alter_table``.
    """
    op.drop_index("idx_edges_temporal", table_name="edges")
    op.drop_index("idx_nodes_temporal", table_name="nodes")

    with op.batch_alter_table("edges") as batch_op:
        batch_op.drop_column("valid_to_sha")
        batch_op.drop_column("valid_from_sha")

    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("valid_to_sha")
        batch_op.drop_column("valid_from_sha")
