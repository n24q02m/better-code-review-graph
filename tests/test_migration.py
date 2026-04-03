import sqlite3

from better_code_review_graph.embeddings import EmbeddingStore


def test_embedding_store_migration_adds_provider_column(tmp_path):
    """Test that EmbeddingStore correctly migrates an old DB by adding the 'provider' column."""
    db_path = tmp_path / "old_embeddings.db"

    # 1. Create an old version of the database manually (missing 'provider' column)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE embeddings (
            qualified_name TEXT PRIMARY KEY,
            vector BLOB NOT NULL,
            text_hash TEXT NOT NULL
        )
    """)
    # Insert a row to ensure data is preserved and default value is applied during migration
    conn.execute(
        "INSERT INTO embeddings (qualified_name, vector, text_hash) VALUES (?, ?, ?)",
        ("old_node", b"old_vector", "old_hash")
    )
    conn.commit()
    conn.close()

    # 2. Initialize EmbeddingStore, which should trigger the migration
    store = EmbeddingStore(db_path)

    # 3. Verify the 'provider' column now exists and has the default value for old rows
    row = store._conn.execute(
        "SELECT provider FROM embeddings WHERE qualified_name = 'old_node'"
    ).fetchone()
    assert row is not None
    assert row["provider"] == "unknown"

    # 4. Verify new inserts also work with the default value
    store._conn.execute(
        "INSERT INTO embeddings (qualified_name, vector, text_hash) VALUES (?, ?, ?)",
        ("new_node", b"new_vector", "new_hash")
    )
    store._conn.commit()
    row = store._conn.execute(
        "SELECT provider FROM embeddings WHERE qualified_name = 'new_node'"
    ).fetchone()
    assert row is not None
    assert row["provider"] == "unknown"

    store.close()
