"""Security tags: add nullable security_tags JSON column on nodes (Phase 3 Task 2).

Adds a single TEXT column ``nodes.security_tags`` to hold a JSON-encoded
array of tag strings (e.g. ``["cwe-89:HIGH", "sink:sql"]``) that the
Phase 3 Task 3+ heuristic scanner will populate. The column is purely
additive on the data path:

* ``security_tags`` is **NULLable with no default**. The semantics
  matter: ``NULL`` means "this node has not been scanned" while
  ``"[]"`` (an empty JSON array) means "scanned, no tags found". A
  ``server_default`` of ``"[]"`` would collapse those two states and
  defeat re-scan detection in the scanner; we therefore leave the
  default off and let the scanner write ``"[]"`` explicitly.
* No source code in this revision writes the column — ``upsert_node``
  is intentionally untouched. Phase 3 Task 3 wires the scanner up.
* Storage is plain ``TEXT`` (not JSON1) for consistency with the
  existing ``extra`` column, which is also a JSON-in-TEXT field. We
  don't rely on SQLite's JSON1 functions anywhere in the read path.

SQLite limitations
------------------
SQLite < 3.35 cannot ``ALTER TABLE DROP COLUMN`` natively. The
downgrade path therefore wraps ``nodes`` in ``op.batch_alter_table``
which performs the create-new-table-copy-drop-old-rename dance under
the hood. The env.py already sets ``render_as_batch=True`` so column
adds are also rendered through the batch mechanism, which is fine for
the additive direction.

The legacy in-code ``_SCHEMA_SQL`` constant in ``graph.py`` is
intentionally NOT updated for this migration — it remains frozen at
v1.6 (the post-002 alembic state) per the Phase 2 design and is now
only consulted as a smoke comparator. The parity gate in
``test_alembic_baseline.py::test_schema_sql_matches_alembic_migrations``
is pinned at revision ``002`` for exactly this reason; ``003`` and
``004`` schema differences from ``_SCHEMA_SQL`` are expected.

Revision ID: 004
Revises: 003
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``nodes.security_tags`` TEXT column."""
    op.add_column(
        "nodes",
        sa.Column("security_tags", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop ``nodes.security_tags``.

    SQLite < 3.35 lacks native ``ALTER TABLE DROP COLUMN`` so the
    column drop is wrapped in ``op.batch_alter_table``, which performs
    a create-new-table-copy-drop-old-rename under the hood.
    """
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("security_tags")
