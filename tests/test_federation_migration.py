"""Tests for the 003_federation alembic migration (Phase 2 Task 1).

These tests verify the additive federation schema introduced in revision
``003``:

* ``nodes.repo_id`` and ``edges.repo_id`` columns (TEXT, NOT NULL,
  default ``''``) are added by the upgrade.
* The ``repos`` registry table is created with the columns spelled out in
  the v2 design spec section 5.4.
* The cross-repo scoping indexes ``idx_nodes_repo_kind`` and
  ``idx_edges_repo`` are created.
* A round-trip (upgrade -> downgrade -> upgrade) leaves no orphan columns
  or tables behind. SQLite cannot natively ``ALTER TABLE DROP COLUMN``
  before 3.35, so the migration uses ``op.batch_alter_table`` for the
  downgrade path; this test covers that branch.
* Existing ``upsert_node`` writes after the upgrade default ``repo_id``
  to ``''`` (single-repo / non-federated mode).
"""

from __future__ import annotations

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


def _index_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(str(db_path))) as conn:
        return {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }


def _table_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(str(db_path))) as conn:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def _index_columns(db_path: Path, index: str) -> list[str]:
    """Return the column names covered by ``index`` in PRAGMA order."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        rows = conn.execute(f"PRAGMA index_info({index})").fetchall()
    # PRAGMA index_info returns (seqno, cid, name) sorted by seqno.
    return [row[2] for row in sorted(rows, key=lambda r: r[0])]


# ---------------------------------------------------------------------------
# Column adds
# ---------------------------------------------------------------------------


def test_federation_migration_adds_repo_id_columns(tmp_path: Path) -> None:
    """``nodes.repo_id`` and ``edges.repo_id`` exist after upgrade.

    Both columns must be TEXT, NOT NULL, with default ``''`` per design
    spec section 5.4 line 187-188.
    """
    db_path = tmp_path / "g.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    nodes_repo = _column_info(db_path, "nodes", "repo_id")
    edges_repo = _column_info(db_path, "edges", "repo_id")

    assert nodes_repo is not None, "nodes.repo_id missing after upgrade"
    assert edges_repo is not None, "edges.repo_id missing after upgrade"

    # (name, type, notnull, dflt, pk)
    name, typ, notnull, dflt, pk = nodes_repo
    assert typ.upper() == "TEXT"
    assert notnull == 1, f"nodes.repo_id must be NOT NULL, got notnull={notnull}"
    assert dflt is not None, "nodes.repo_id must have a default value"
    assert dflt.strip("'\"") == "", f"default should be empty string, got {dflt!r}"
    assert pk == 0

    name, typ, notnull, dflt, pk = edges_repo
    assert typ.upper() == "TEXT"
    assert notnull == 1
    assert dflt is not None
    assert dflt.strip("'\"") == ""
    assert pk == 0


# ---------------------------------------------------------------------------
# repos table
# ---------------------------------------------------------------------------


def test_federation_migration_creates_repos_table(tmp_path: Path) -> None:
    """The ``repos`` registry table exists with exactly the spec columns."""
    db_path = tmp_path / "g.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    assert "repos" in _table_names(db_path), "repos table missing after upgrade"

    columns = {row[0]: row for row in _table_info(db_path, "repos")}
    expected = {
        "repo_id",
        "path",
        "remote_url",
        "last_indexed_sha",
        "first_indexed_at",
        "last_indexed_at",
    }
    assert expected.issubset(set(columns.keys())), (
        f"missing columns: {expected - set(columns.keys())}"
    )

    # repo_id: TEXT PRIMARY KEY NOT NULL
    name, typ, notnull, dflt, pk = columns["repo_id"]
    assert typ.upper() == "TEXT"
    assert pk == 1, "repo_id must be primary key"

    # path: TEXT NOT NULL
    name, typ, notnull, dflt, pk = columns["path"]
    assert typ.upper() == "TEXT"
    assert notnull == 1

    # remote_url: TEXT NULL
    name, typ, notnull, dflt, pk = columns["remote_url"]
    assert typ.upper() == "TEXT"
    assert notnull == 0

    # last_indexed_sha: TEXT NULL
    name, typ, notnull, dflt, pk = columns["last_indexed_sha"]
    assert typ.upper() == "TEXT"
    assert notnull == 0

    # first_indexed_at: INTEGER NOT NULL
    name, typ, notnull, dflt, pk = columns["first_indexed_at"]
    assert typ.upper() == "INTEGER"
    assert notnull == 1

    # last_indexed_at: INTEGER NOT NULL
    name, typ, notnull, dflt, pk = columns["last_indexed_at"]
    assert typ.upper() == "INTEGER"
    assert notnull == 1


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


def test_federation_migration_creates_indexes(tmp_path: Path) -> None:
    """Both federation indexes exist and cover the documented columns.

    * ``idx_nodes_repo_kind`` on ``nodes(repo_id, kind)`` per spec
      section 5.4 line 193.
    * ``idx_edges_repo`` on ``edges(repo_id)`` (single-column analog —
      we don't have a kind-shaped query for edges yet).
    """
    db_path = tmp_path / "g.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    indexes = _index_names(db_path)
    assert "idx_nodes_repo_kind" in indexes
    assert "idx_edges_repo" in indexes

    assert _index_columns(db_path, "idx_nodes_repo_kind") == ["repo_id", "kind"]
    assert _index_columns(db_path, "idx_edges_repo") == ["repo_id"]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_federation_migration_round_trip(tmp_path: Path) -> None:
    """upgrade -> downgrade("002") -> upgrade restores the schema cleanly.

    SQLite < 3.35 cannot natively ``ALTER TABLE DROP COLUMN``; the
    migration uses ``op.batch_alter_table`` for the downgrade path.
    After the downgrade, neither ``repo_id`` columns nor the ``repos``
    table nor the federation indexes may remain.
    """
    db_path = tmp_path / "g.db"
    cfg = _alembic_config_for(db_path)

    # Up -> assert federation pieces present.
    command.upgrade(cfg, "head")
    assert _column_info(db_path, "nodes", "repo_id") is not None
    assert _column_info(db_path, "edges", "repo_id") is not None
    assert "repos" in _table_names(db_path)
    indexes_up = _index_names(db_path)
    assert "idx_nodes_repo_kind" in indexes_up
    assert "idx_edges_repo" in indexes_up

    # Down to 002 -> federation pieces gone, baseline preserved.
    command.downgrade(cfg, "002")
    assert _column_info(db_path, "nodes", "repo_id") is None, (
        "nodes.repo_id leaked through downgrade"
    )
    assert _column_info(db_path, "edges", "repo_id") is None, (
        "edges.repo_id leaked through downgrade"
    )
    assert "repos" not in _table_names(db_path), "repos table leaked through downgrade"
    indexes_down = _index_names(db_path)
    assert "idx_nodes_repo_kind" not in indexes_down
    assert "idx_edges_repo" not in indexes_down
    # Baseline tables and indexes preserved.
    assert "nodes" in _table_names(db_path)
    assert "edges" in _table_names(db_path)
    assert "metadata" in _table_names(db_path)
    assert "idx_nodes_kind" in indexes_down
    assert "idx_edges_kind" in indexes_down

    # Up again -> federation pieces restored.
    command.upgrade(cfg, "head")
    assert _column_info(db_path, "nodes", "repo_id") is not None
    assert _column_info(db_path, "edges", "repo_id") is not None
    assert "repos" in _table_names(db_path)
    indexes_up_again = _index_names(db_path)
    assert "idx_nodes_repo_kind" in indexes_up_again
    assert "idx_edges_repo" in indexes_up_again


# ---------------------------------------------------------------------------
# Default value applied via public API
# ---------------------------------------------------------------------------


def test_federation_migration_default_value(tmp_path: Path) -> None:
    """A row inserted via ``GraphStore.upsert_node`` has ``repo_id=''``.

    ``upsert_node`` does not (yet) populate ``repo_id`` explicitly — the
    column relies on the SQL ``DEFAULT ''`` clause. This test guards
    against the migration accidentally omitting the default value, which
    would force every existing call site to be modified before single-
    repo mode keeps working.
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
            "SELECT repo_id FROM nodes WHERE qualified_name = ?",
            ("src/sample.py::default_check",),
        ).fetchone()
        assert row is not None, "upserted node should be retrievable"
        assert row["repo_id"] == "", (
            f"repo_id default should be empty string, got {row['repo_id']!r}"
        )
    finally:
        store.close()
