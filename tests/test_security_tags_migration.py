"""Tests for the 004_security_tags alembic migration (Phase 3 Task 2).

Revision ``004`` is purely additive: it adds a single nullable
``security_tags`` TEXT column to the ``nodes`` table. The column stores
a JSON-serialized array of tag strings (e.g.
``["cwe-89:HIGH", "sink:sql"]``) once the Phase 3 Task 3+ heuristic
scanner starts populating it. For now no source code writes the column
— the migration just lands the storage slot.

These tests cover:

* ``security_tags`` column exists after upgrade with the documented
  shape (TEXT, NULL allowed, no default).
* The column accepts a JSON-array string round-trip via raw SQL.
* Newly inserted rows (without an explicit value) have
  ``security_tags IS NULL`` — confirms the column has no default that
  would shadow ``None`` writes from the Phase 3 scanner later.
* upgrade(head) -> downgrade("003") -> upgrade(head) leaves no orphan
  column behind. SQLite < 3.35 cannot natively ``ALTER TABLE
  DROP COLUMN``; the migration uses ``op.batch_alter_table`` for the
  downgrade path and this test exercises that branch.
* A synthetic legacy DB stamped at ``003`` (with all Phase 2 federation
  columns already in place) still upgrades cleanly to head — the
  migration must not assume a fresh-DB starting state.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo


def _alembic_config_for(db_path: Path) -> Config:
    """Build an Alembic Config bound to ``db_path`` using the project ini."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _table_info(db_path: Path, table: str) -> list[tuple]:
    """Return PRAGMA table_info rows as (name, type, notnull, dflt, pk)."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [
        (name, typ, notnull, dflt, pk) for (_cid, name, typ, notnull, dflt, pk) in rows
    ]


def _column_info(db_path: Path, table: str, column: str) -> tuple | None:
    """Return the (name, type, notnull, dflt, pk) tuple for a single column."""
    for row in _table_info(db_path, table):
        if row[0] == column:
            return row
    return None


# ---------------------------------------------------------------------------
# Column shape after upgrade
# ---------------------------------------------------------------------------


def test_security_tags_column_exists_after_migration(tmp_path: Path) -> None:
    """``nodes.security_tags`` exists after upgrade — TEXT, NULLABLE, no default.

    The column will hold a JSON-encoded array of tag strings; we
    deliberately keep it a plain ``TEXT`` (not JSON1) to stay consistent
    with how ``extra`` is stored, and we leave it NULLable + no default
    so Phase 3 scanner code can distinguish "never scanned" (NULL) from
    "scanned, no tags" (``"[]"``).
    """
    db_path = tmp_path / "g.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    info = _column_info(db_path, "nodes", "security_tags")
    assert info is not None, "nodes.security_tags missing after upgrade"

    name, typ, notnull, dflt, pk = info
    assert name == "security_tags"
    assert typ.upper() == "TEXT"
    assert notnull == 0, f"nodes.security_tags must be NULLable, got notnull={notnull}"
    assert dflt is None, f"nodes.security_tags must have no default, got dflt={dflt!r}"
    assert pk == 0


# ---------------------------------------------------------------------------
# JSON-array round-trip via raw SQL
# ---------------------------------------------------------------------------


def test_security_tags_accepts_json_array(tmp_path: Path) -> None:
    """The column round-trips a JSON-array string via raw SQL.

    We don't use SQLite's JSON1 extension here — the storage contract is
    "TEXT containing whatever the writer encoded", same as ``extra``.
    The Phase 3 scanner will be the writer; this test just guards that
    the column can hold a representative payload.
    """
    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    try:
        node = NodeInfo(
            kind="Function",
            name="vulnerable_query",
            file_path="src/db.py",
            line_start=1,
            line_end=10,
            language="python",
        )
        store.upsert_node(node)

        payload = ["cwe-89:HIGH", "sink:sql", "tainted-input"]
        encoded = json.dumps(payload)

        store._conn.execute(
            "UPDATE nodes SET security_tags = ? WHERE qualified_name = ?",
            (encoded, "src/db.py::vulnerable_query"),
        )
        store._conn.commit()

        row = store._conn.execute(
            "SELECT security_tags FROM nodes WHERE qualified_name = ?",
            ("src/db.py::vulnerable_query",),
        ).fetchone()
        assert row is not None, "upserted node should be retrievable"
        assert row["security_tags"] == encoded, (
            f"raw round-trip mismatch: stored {encoded!r}, got {row['security_tags']!r}"
        )
        assert json.loads(row["security_tags"]) == payload
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Default value
# ---------------------------------------------------------------------------


def test_security_tags_default_is_null(tmp_path: Path) -> None:
    """Newly inserted nodes have ``security_tags IS NULL`` by default.

    ``upsert_node`` does not (and must not, until Phase 3 Task 3+ wires
    the heuristic scanner) write to ``security_tags``. The column must
    therefore default to NULL — guarding against the migration
    accidentally adding a ``server_default`` that would shadow real
    ``None`` writes from the future scanner.
    """
    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    try:
        node = NodeInfo(
            kind="Function",
            name="default_check",
            file_path="src/sample.py",
            line_start=1,
            line_end=5,
            language="python",
        )
        store.upsert_node(node)

        row = store._conn.execute(
            "SELECT security_tags FROM nodes WHERE qualified_name = ?",
            ("src/sample.py::default_check",),
        ).fetchone()
        assert row is not None, "upserted node should be retrievable"
        assert row["security_tags"] is None, (
            f"security_tags default should be NULL, got {row['security_tags']!r}"
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Round-trip upgrade -> downgrade -> upgrade
# ---------------------------------------------------------------------------


def test_004_round_trip_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    """upgrade(head) -> downgrade("003") -> upgrade(head) leaves no orphans.

    SQLite < 3.35 lacks native ``ALTER TABLE DROP COLUMN``; the
    migration uses ``op.batch_alter_table`` for the downgrade path.
    This test asserts that:

    * After upgrade head, ``security_tags`` exists.
    * After downgrade to ``003``, ``security_tags`` is gone but every
      Phase 2 federation column / index / table is preserved.
    * After re-upgrade to head, ``security_tags`` is restored.
    """
    db_path = tmp_path / "g.db"
    cfg = _alembic_config_for(db_path)

    # Up -> security_tags present.
    command.upgrade(cfg, "head")
    assert _column_info(db_path, "nodes", "security_tags") is not None

    # Down to 003 -> security_tags gone, Phase 2 federation pieces preserved.
    command.downgrade(cfg, "003")
    assert _column_info(db_path, "nodes", "security_tags") is None, (
        "nodes.security_tags leaked through downgrade"
    )
    # Phase 2 federation pieces survive the downgrade.
    assert _column_info(db_path, "nodes", "repo_id") is not None
    assert _column_info(db_path, "edges", "repo_id") is not None
    with closing(sqlite3.connect(str(db_path))) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }
    assert "repos" in tables
    assert "idx_nodes_repo_kind" in indexes
    assert "idx_edges_repo" in indexes

    # Up again -> security_tags restored.
    command.upgrade(cfg, "head")
    assert _column_info(db_path, "nodes", "security_tags") is not None


# ---------------------------------------------------------------------------
# Legacy DB stamped at 003 still upgrades cleanly to head
# ---------------------------------------------------------------------------


def test_004_legacy_db_still_works(tmp_path: Path) -> None:
    """A DB stamped at ``003`` (Phase 2 federation in place) upgrades to head.

    Builds a synthetic DB by upgrading head then downgrading to 003 —
    that yields the post-Phase-2 schema with ``alembic_version`` already
    pointing at ``003``. Re-running ``upgrade head`` then walks the
    single 003 -> 004 step; this is the production code path for any
    install that landed Phase 2 before Phase 3.
    """
    db_path = tmp_path / "legacy.db"
    cfg = _alembic_config_for(db_path)

    # Build a Phase 2 (rev 003) state.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "003")
    assert _column_info(db_path, "nodes", "security_tags") is None
    # Sanity-check: stamped at 003.
    with closing(sqlite3.connect(str(db_path))) as conn:
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert rev is not None and rev[0] == "003", (
            f"expected stamped at 003, got {rev}"
        )

    # Production path: upgrade head walks 003 -> 004.
    command.upgrade(cfg, "head")
    info = _column_info(db_path, "nodes", "security_tags")
    assert info is not None, "security_tags missing after upgrading legacy 003 DB"
    name, typ, notnull, dflt, pk = info
    assert typ.upper() == "TEXT"
    assert notnull == 0
    assert dflt is None
