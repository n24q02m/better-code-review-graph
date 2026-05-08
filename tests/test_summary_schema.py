"""Schema tests for Phase 1 v1.6.x LLM-summary columns on the nodes table.

Phase 1 adds three nullable columns and an index to support cached LLM
summaries:
- summary TEXT NULL
- summary_provider TEXT NULL
- source_hash TEXT NULL
- INDEX idx_nodes_source_hash ON nodes(source_hash)
"""

import sqlite3

from better_code_review_graph.graph import GraphStore


def test_summary_columns_exist(tmp_path):
    store = GraphStore(str(tmp_path / "test.db"))
    try:
        cols = {
            row[1] for row in store._conn.execute("PRAGMA table_info(nodes)").fetchall()
        }
        assert "summary" in cols
        assert "summary_provider" in cols
        assert "source_hash" in cols
    finally:
        store.close()


def test_source_hash_index_exists(tmp_path):
    store = GraphStore(str(tmp_path / "test.db"))
    try:
        rows = store._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_nodes_source_hash'"
        ).fetchall()
        assert len(rows) == 1
    finally:
        store.close()


def test_legacy_db_migration_preserves_rows(tmp_path):
    """A nodes table created without the v1.6 columns should be migrated in place."""
    db_path = tmp_path / "legacy.db"
    # Create a v1.5-style nodes table missing summary/summary_provider/source_hash.
    # Use a minimal compatible subset of columns that GraphStore upsert_node populates.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE nodes(
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL UNIQUE,
            file_path TEXT NOT NULL,
            line_start INTEGER,
            line_end INTEGER,
            language TEXT,
            parent_name TEXT,
            params TEXT,
            return_type TEXT,
            modifiers TEXT,
            is_test INTEGER,
            file_hash TEXT,
            extra TEXT,
            updated_at REAL
        )"""
    )
    conn.execute(
        "INSERT INTO nodes(kind, name, qualified_name, file_path, line_start, line_end, language, "
        "parent_name, params, return_type, modifiers, is_test, file_hash, extra, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "Function",
            "old_fn",
            "src/x.py::old_fn",
            "src/x.py",
            1,
            3,
            "python",
            None,
            None,
            None,
            None,
            0,
            "h",
            "{}",
            0.0,
        ),
    )
    conn.commit()
    conn.close()

    # Open via GraphStore -- should run _ensure_summary_columns and migrate.
    store = GraphStore(str(db_path))
    try:
        cols = {
            row[1] for row in store._conn.execute("PRAGMA table_info(nodes)").fetchall()
        }
        assert {"summary", "summary_provider", "source_hash"} <= cols

        # Index present.
        idx = store._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_nodes_source_hash'"
        ).fetchall()
        assert len(idx) == 1

        # Pre-existing row preserved.
        rows = store._conn.execute(
            "SELECT name FROM nodes WHERE qualified_name = 'src/x.py::old_fn'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "old_fn"
    finally:
        store.close()


def test_ensure_summary_columns_is_idempotent(tmp_path):
    """Reopening the same GraphStore must not error and must not duplicate the index."""
    db_path = tmp_path / "double_open.db"

    store1 = GraphStore(str(db_path))
    store1.close()

    store2 = GraphStore(str(db_path))
    try:
        cols = {
            row[1]
            for row in store2._conn.execute("PRAGMA table_info(nodes)").fetchall()
        }
        assert {"summary", "summary_provider", "source_hash"} <= cols

        idx_count = store2._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='index' AND name='idx_nodes_source_hash'"
        ).fetchone()[0]
        assert idx_count == 1
    finally:
        store2.close()
