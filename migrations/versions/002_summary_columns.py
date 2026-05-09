"""Phase 1 summary columns recorded as a no-op stamp target.

Phase 1 v1.6.x added four summary columns (``summary``, ``summary_provider``,
``source_hash``, ``source_text``) to the ``nodes`` table. The Phase 1
implementation shipped these by extending the inline ``_SCHEMA_SQL`` constant
plus an idempotent runtime helper ``GraphStore._ensure_summary_columns``;
alembic was not wired up at the time.

This revision exists purely so legacy DBs created by that helper can be
``alembic stamp 002``-ed before being upgraded — without it, alembic would
walk back to the baseline and try to re-create columns that already exist.

The baseline migration (``001``) already includes these columns in its
``CREATE TABLE nodes`` statement, so on a fresh DB upgrade chain
001 -> 002 leaves the schema unchanged. Both ``upgrade`` and ``downgrade``
are intentional no-ops.

Revision ID: 002
Revises: 001
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: columns already defined in 001_baseline.

    Kept as a stamp target for legacy DBs created by Phase 1 v1.6.x's
    ``GraphStore._ensure_summary_columns`` helper before alembic adoption.
    """
    pass


def downgrade() -> None:
    """No-op: we never want to remove the summary columns."""
    pass
