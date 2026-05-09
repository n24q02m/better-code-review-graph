"""Federation: add repo_id columns + repos registry table (Phase 2 Task 1).

Adds the cross-repo scoping primitives from the v2 design spec section
5.4. The migration is purely additive on the data path:

* ``nodes.repo_id`` (TEXT NOT NULL DEFAULT '') — every node now declares
  the repo it belongs to. The default ``''`` keeps single-repo /
  non-federated mode working without runtime changes; the federation
  driver (Phase 2 Task 2 onwards) populates the column on ingest.
* ``edges.repo_id`` (TEXT NOT NULL DEFAULT '') — same shape, same
  default, same rationale.
* ``repos`` registry table — populated only when federation is enabled.
  For non-federated installs the table exists but stays empty.
* ``idx_nodes_repo_kind`` on ``nodes(repo_id, kind)`` — the canonical
  scoped lookup pattern from spec section 5.4 line 193.
* ``idx_edges_repo`` on ``edges(repo_id)`` — single-column analog for
  edge scoping. There is no kind-shaped query for edges yet, so we
  index just ``repo_id`` and let the query planner pick from there.

SQLite limitations
------------------
SQLite < 3.35 cannot ``ALTER TABLE DROP COLUMN`` natively. The
downgrade path therefore wraps each table in
``op.batch_alter_table`` which performs the
create-new-table-copy-drop-old-rename dance under the hood. The env.py
already sets ``render_as_batch=True`` so column adds are also rendered
through the batch mechanism, which is fine for the additive direction.

The legacy in-code ``_SCHEMA_SQL`` constant in ``graph.py`` is
intentionally NOT updated for this migration — it remains frozen at
v1.6 (the post-002 alembic state) per the Phase 2 design and is now
only consulted as a smoke comparator. Any future schema change goes
through alembic only.

Revision ID: 003
Revises: 002
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add repo_id columns, repos table, and federation indexes."""
    # Additive column on nodes — NOT NULL with empty-string default so
    # existing single-repo rows backfill cleanly.
    op.add_column(
        "nodes",
        sa.Column(
            "repo_id",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )

    # Same shape on edges.
    op.add_column(
        "edges",
        sa.Column(
            "repo_id",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )

    # Registry table. ``repo_id`` is the natural primary key (the slug
    # the federation driver coins from the remote URL or local path).
    # ``first_indexed_at`` and ``last_indexed_at`` are unix timestamps
    # stored as INTEGER, mirroring the spec section 5.4.
    op.create_table(
        "repos",
        sa.Column("repo_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("remote_url", sa.Text(), nullable=True),
        sa.Column("last_indexed_sha", sa.Text(), nullable=True),
        sa.Column("first_indexed_at", sa.Integer(), nullable=False),
        sa.Column("last_indexed_at", sa.Integer(), nullable=False),
    )

    # Scoped lookup indexes — see module docstring for naming rationale.
    op.create_index("idx_nodes_repo_kind", "nodes", ["repo_id", "kind"])
    op.create_index("idx_edges_repo", "edges", ["repo_id"])


def downgrade() -> None:
    """Drop federation indexes, repos table, then repo_id columns.

    SQLite < 3.35 lacks native ``DROP COLUMN`` so each table is wrapped
    in ``op.batch_alter_table``. The order matters: drop indexes
    BEFORE dropping the columns they reference, drop the standalone
    ``repos`` table independently.
    """
    op.drop_index("idx_edges_repo", table_name="edges")
    op.drop_index("idx_nodes_repo_kind", table_name="nodes")

    op.drop_table("repos")

    with op.batch_alter_table("edges") as batch_op:
        batch_op.drop_column("repo_id")

    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("repo_id")
