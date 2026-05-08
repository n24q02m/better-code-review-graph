"""Schema tests for Phase 1 v1.6.x LLM-summary columns on the nodes table.

Phase 1 adds three nullable columns and an index to support cached LLM
summaries:
- summary TEXT NULL
- summary_provider TEXT NULL
- source_hash TEXT NULL
- INDEX idx_nodes_source_hash ON nodes(source_hash)
"""

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
