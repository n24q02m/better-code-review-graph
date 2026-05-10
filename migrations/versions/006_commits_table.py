"""Commits table for first-parent commit history (Phase 3 Task 7).

Adds the ``commits`` table from spec section 5.4. The table records the
mainline commit chain (``git log --first-parent``) for each registered
repo so future v2 query layers can answer "what commits touched the
graph between SHA A and SHA B?" without re-running git for every query.

Schema (additive, non-breaking):

* ``sha`` (TEXT, PRIMARY KEY) — the commit SHA. Globally unique across
  repos in practice; we still scope queries by ``repo_id`` for
  cross-repo hygiene.
* ``repo_id`` (TEXT, NOT NULL) — foreign key to ``repos.repo_id`` (added
  in revision 003). The FK is declared for schema correctness; SQLite
  enforces it only when ``PRAGMA foreign_keys = ON`` (off by default).
* ``parent_sha`` (TEXT, NULL allowed) — the first-parent commit SHA, or
  ``NULL`` for the root commit (no parents).
* ``timestamp`` (INTEGER, NOT NULL) — the commit's authored unix
  timestamp (``%ct``).
* ``message`` (TEXT, NULL allowed) — the commit subject (first line of
  ``%s``). Long descriptions are intentionally not stored; the table is
  for fast SHA→ts lookup, not full message search.
* ``idx_commits_repo_time`` on ``commits(repo_id, timestamp)`` — the
  canonical "commits in repo X between t1 and t2" scan pattern.

Backfill happens on first build via the package-level helper
``federation.backfill_commits_for_repo`` which walks
``git log --first-parent`` for the registered root and bulk-inserts
the rows. The helper uses ``INSERT OR IGNORE`` so re-runs are
idempotent; the migration itself does no data backfill (the table
is empty post-upgrade and gets populated on the next graph build).

Revision ID: 006
Revises: 005
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``commits`` table + ``idx_commits_repo_time`` index."""
    op.create_table(
        "commits",
        sa.Column("sha", sa.Text(), primary_key=True, nullable=False),
        sa.Column("repo_id", sa.Text(), nullable=False),
        sa.Column("parent_sha", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repos.repo_id"],
            name="fk_commits_repo_id",
        ),
    )
    op.create_index(
        "idx_commits_repo_time",
        "commits",
        ["repo_id", "timestamp"],
    )


def downgrade() -> None:
    """Drop ``idx_commits_repo_time`` index then the ``commits`` table.

    Order matters: drop the index before the table it references so
    SQLite does not leave dangling index metadata.
    """
    op.drop_index("idx_commits_repo_time", table_name="commits")
    op.drop_table("commits")
