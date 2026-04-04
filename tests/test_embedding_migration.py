"""Test EmbeddingStore schema migration for old databases lacking the 'provider' column."""

import sqlite3

from better_code_review_graph.embeddings import EmbeddingStore


def test_migration_adds_provider_column(tmp_path):
    """EmbeddingStore should add 'provider' column to old DBs missing it."""
    db_path = tmp_path / "old_embeddings.db"

    # Create old-format DB without 'provider' column
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE embeddings (
            qualified_name TEXT PRIMARY KEY,
            vector BLOB NOT NULL,
            text_hash TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO embeddings (qualified_name, vector, text_hash) VALUES (?, ?, ?)",
        ("old_node", b"\x00" * 16, "abc123"),
    )
    conn.commit()
    conn.close()

    # Opening EmbeddingStore should auto-migrate
    store = EmbeddingStore(db_path)

    # Old row should have default 'unknown' provider
    row = store._conn.execute(
        "SELECT provider FROM embeddings WHERE qualified_name = 'old_node'"
    ).fetchone()
    assert row is not None
    assert row["provider"] == "unknown"

    # New inserts should also work
    store._conn.execute(
        "INSERT INTO embeddings (qualified_name, vector, text_hash) VALUES (?, ?, ?)",
        ("new_node", b"\x00" * 16, "def456"),
    )
    store._conn.commit()
    row = store._conn.execute(
        "SELECT provider FROM embeddings WHERE qualified_name = 'new_node'"
    ).fetchone()
    assert row is not None
    assert row["provider"] == "unknown"

    store.close()
