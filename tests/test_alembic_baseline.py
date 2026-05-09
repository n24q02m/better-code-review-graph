"""Tests for the Alembic baseline migration (Phase 2 Task 0).

These tests exercise four distinct paths:

* (a) Fresh DB created via ``GraphStore`` reaches alembic head and contains
  every table, index, and Phase 1 summary column from ``_SCHEMA_SQL``.
* (b) Re-initialising ``GraphStore`` on the same DB is idempotent.
* (c) ``downgrade("base")`` followed by ``upgrade("head")`` round-trips
  cleanly without orphaning tables, indexes, or columns.
* (d) A synthetic legacy DB that already has the Phase 1 columns (because
  it was created by ``_SCHEMA_SQL`` + ``_ensure_summary_columns``) can be
  stamped at revision ``002`` and then upgraded to head without DDL
  conflict.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from better_code_review_graph.graph import _SCHEMA_SQL, GraphStore

# All tables and indexes that the baseline migration is expected to create.
EXPECTED_TABLES = {"nodes", "edges", "metadata"}
EXPECTED_INDEXES = {
    "idx_nodes_file",
    "idx_nodes_kind",
    "idx_nodes_qualified",
    "idx_edges_source",
    "idx_edges_target",
    "idx_edges_kind",
    "idx_edges_file",
}
SUMMARY_COLUMNS = {"summary", "summary_provider", "source_hash", "source_text"}


def _alembic_config_for(db_path: Path) -> Config:
    """Build an Alembic Config bound to ``db_path`` using the project ini."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _current_revision(db_path: Path) -> str | None:
    """Return the revision recorded in ``alembic_version`` (or None)."""
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if row is None:
            return None
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return rev[0] if rev else None


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def _index_names(db_path: Path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        return {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }


def _columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _head_revision() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    assert head is not None, "alembic must report a head revision"
    return head


# ---------------------------------------------------------------------------
# (a) fresh DB
# ---------------------------------------------------------------------------


def test_fresh_db_reaches_head_with_full_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    try:
        # Alembic version table reports head.
        head = _head_revision()
        assert _current_revision(db_path) == head

        # All structural tables present (alembic_version is the bookkeeping
        # table — not part of the application schema).
        tables = _table_names(db_path)
        assert EXPECTED_TABLES.issubset(tables)
        assert "alembic_version" in tables

        # All named indexes present (idx_nodes_source_hash is created by the
        # legacy `_ensure_summary_columns` helper, not by the baseline; it is
        # therefore not enforced here, but if present we tolerate it).
        idx = _index_names(db_path)
        assert EXPECTED_INDEXES.issubset(idx)

        # All four Phase 1 summary columns present.
        cols = _columns(db_path, "nodes")
        assert SUMMARY_COLUMNS.issubset(cols)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# (b) re-init idempotent
# ---------------------------------------------------------------------------


def test_reinit_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"

    store1 = GraphStore(db_path)
    try:
        first_tables = _table_names(db_path)
        first_idx = _index_names(db_path)
        first_cols = _columns(db_path, "nodes")
    finally:
        store1.close()

    store2 = GraphStore(db_path)
    try:
        assert _table_names(db_path) == first_tables
        assert _index_names(db_path) == first_idx
        assert _columns(db_path, "nodes") == first_cols
        # Still at head — no extra revision rows.
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM alembic_version").fetchone()[0]
        assert count == 1
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# (c) downgrade -> upgrade round-trip
# ---------------------------------------------------------------------------


def test_downgrade_then_upgrade_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    store.close()

    cfg = _alembic_config_for(db_path)

    # Downgrade to base — should drop nodes/edges/metadata + indexes.
    command.downgrade(cfg, "base")
    tables_after_down = _table_names(db_path)
    assert not (EXPECTED_TABLES & tables_after_down), (
        f"orphan tables after downgrade: {EXPECTED_TABLES & tables_after_down}"
    )
    indexes_after_down = _index_names(db_path)
    assert not (EXPECTED_INDEXES & indexes_after_down), (
        f"orphan indexes after downgrade: {EXPECTED_INDEXES & indexes_after_down}"
    )

    # Upgrade back to head — full schema restored.
    command.upgrade(cfg, "head")
    assert _current_revision(db_path) == _head_revision()
    assert EXPECTED_TABLES.issubset(_table_names(db_path))
    assert EXPECTED_INDEXES.issubset(_index_names(db_path))
    assert SUMMARY_COLUMNS.issubset(_columns(db_path, "nodes"))


# ---------------------------------------------------------------------------
# (d) synthetic legacy DB stamped at 002
# ---------------------------------------------------------------------------


def test_legacy_db_stamped_at_002_reaches_head(tmp_path: Path) -> None:
    """Simulate a DB created by Phase 1 v1.6.x (executescript + ALTER TABLE).

    Such a DB already has every column the baseline + 002 migration would
    create. We stamp it at 002 (the last hand-authored revision the legacy
    helper effectively brought it to) then upgrade to head; this must
    succeed with no DDL conflict.
    """
    db_path = tmp_path / "legacy.db"

    # Manually replay the Phase 1 schema: _SCHEMA_SQL already includes the
    # summary columns since v1.6, so no ALTER TABLE is needed for a
    # representative legacy DB. We deliberately do NOT create
    # alembic_version here — that is the point of the stamp.
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    assert _current_revision(db_path) is None
    assert SUMMARY_COLUMNS.issubset(_columns(db_path, "nodes"))

    cfg = _alembic_config_for(db_path)
    command.stamp(cfg, "002")
    assert _current_revision(db_path) == "002"

    # Upgrade to head — must be a no-op DDL-wise (we are already there) but
    # alembic should still process the chain without raising.
    command.upgrade(cfg, "head")
    assert _current_revision(db_path) == _head_revision()

    # Schema unchanged (still has summary columns and all structural
    # tables/indexes).
    assert EXPECTED_TABLES.issubset(_table_names(db_path))
    assert EXPECTED_INDEXES.issubset(_index_names(db_path))
    assert SUMMARY_COLUMNS.issubset(_columns(db_path, "nodes"))


# ---------------------------------------------------------------------------
# Cross-check: `alembic current` matches MigrationContext
# ---------------------------------------------------------------------------


def test_alembic_current_via_runtime_context(tmp_path: Path) -> None:
    """``MigrationContext.get_current_revision`` agrees with our helper."""
    from sqlalchemy import create_engine

    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    try:
        cfg = _alembic_config_for(db_path)
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                assert ctx.get_current_revision() == _head_revision()
        finally:
            engine.dispose()
        # Sanity — make sure cfg is usable (alembic.command.current does not
        # return a value, so we just confirm it does not raise).
        command.current(cfg)
    finally:
        store.close()


@pytest.mark.parametrize(
    "missing_arg",
    [None, "head"],
)
def test_alembic_config_resolves(missing_arg: str | None, tmp_path: Path) -> None:
    """Smoke check that the project's alembic.ini + migrations dir are wired
    correctly regardless of which revision label callers ask for."""
    db_path = tmp_path / "smoke.db"
    cfg = _alembic_config_for(db_path)
    target = missing_arg or "head"
    command.upgrade(cfg, target)
    assert _current_revision(db_path) == _head_revision()
