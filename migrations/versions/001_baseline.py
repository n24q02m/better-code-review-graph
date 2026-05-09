"""Baseline schema (Phase 2 Task 0).

This migration mirrors ``better_code_review_graph.graph._SCHEMA_SQL`` exactly
so that fresh databases created via alembic are byte-equivalent to those
created by the legacy ``executescript(_SCHEMA_SQL)`` bootstrap. ``_SCHEMA_SQL``
remains as a smoke comparator + safety net for one release; alembic is now
authoritative on fresh DBs.

The schema covers:

* ``nodes`` — 19 columns (15 original + 4 Phase 1 summary columns
  ``summary``, ``summary_provider``, ``source_hash``, ``source_text``).
* ``edges`` — 8 columns.
* ``metadata`` — 2 columns.
* 7 named indexes (``idx_nodes_file/kind/qualified`` and
  ``idx_edges_source/target/kind/file``).

The eighth index ``idx_nodes_source_hash`` is intentionally NOT created
here. It is created by the runtime helper
``GraphStore._ensure_summary_columns()`` (kept as a defensive idempotent
guard for any DB created between Phase 1 ship and alembic adoption). The
hand-authored 002 migration also stays a no-op for the same reason.

Revision ID: 001
Revises:
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the baseline graph schema (nodes, edges, metadata + indexes)."""
    op.create_table(
        "nodes",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False, unique=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("parent_name", sa.Text(), nullable=True),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("return_type", sa.Text(), nullable=True),
        sa.Column("modifiers", sa.Text(), nullable=True),
        sa.Column(
            "is_test",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("0"),
        ),
        sa.Column("file_hash", sa.Text(), nullable=True),
        sa.Column(
            "extra",
            sa.Text(),
            nullable=True,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("updated_at", sa.Float(), nullable=False),
        # Phase 1 v1.6.x summary columns — nullable, no defaults.
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_provider", sa.Text(), nullable=True),
        sa.Column("source_hash", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
    )

    op.create_table(
        "edges",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_qualified", sa.Text(), nullable=False),
        sa.Column("target_qualified", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column(
            "line",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "extra",
            sa.Text(),
            nullable=True,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )

    op.create_table(
        "metadata",
        sa.Column("key", sa.Text(), primary_key=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
    )

    op.create_index("idx_nodes_file", "nodes", ["file_path"])
    op.create_index("idx_nodes_kind", "nodes", ["kind"])
    op.create_index("idx_nodes_qualified", "nodes", ["qualified_name"])
    op.create_index("idx_edges_source", "edges", ["source_qualified"])
    op.create_index("idx_edges_target", "edges", ["target_qualified"])
    op.create_index("idx_edges_kind", "edges", ["kind"])
    op.create_index("idx_edges_file", "edges", ["file_path"])


def downgrade() -> None:
    """Drop indexes and tables in reverse creation order."""
    op.drop_index("idx_edges_file", table_name="edges")
    op.drop_index("idx_edges_kind", table_name="edges")
    op.drop_index("idx_edges_target", table_name="edges")
    op.drop_index("idx_edges_source", table_name="edges")
    op.drop_index("idx_nodes_qualified", table_name="nodes")
    op.drop_index("idx_nodes_kind", table_name="nodes")
    op.drop_index("idx_nodes_file", table_name="nodes")

    op.drop_table("metadata")
    op.drop_table("edges")
    op.drop_table("nodes")
