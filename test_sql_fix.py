import json
import sqlite3

class Store:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("CREATE TABLE nodes (name TEXT, qualified_name TEXT, kind TEXT, file_path TEXT, line_start INTEGER, line_end INTEGER)")
        self._conn.execute("INSERT INTO nodes VALUES ('foo', 'foo_qn', 'Function', 'src/foo.py', 1, 100)")
        self._conn.execute("INSERT INTO nodes VALUES ('bar', 'bar_qn', 'Class', 'src/bar.py', 1, 50)")

    def search_nodes(self, query: str, kind: str | None = None, limit: int = 20) -> list:
        words = query.lower().split()
        if not words:
            return []
        rows = self._conn.execute(
            """
            SELECT * FROM nodes
            WHERE (
                SELECT COUNT(*)
                FROM json_each(?)
                WHERE LOWER(nodes.name) LIKE "%" || LOWER(value) || "%"
                   OR LOWER(nodes.qualified_name) LIKE "%" || LOWER(value) || "%"
            ) = (SELECT COUNT(*) FROM json_each(?))
              AND (? IS NULL OR kind = ?)
            ORDER BY name LIMIT ?
            """,
            (json.dumps(words), json.dumps(words), kind, kind, limit),
        ).fetchall()
        return [r['name'] for r in rows]

    def get_nodes_by_size(
        self,
        min_lines: int = 50,
        max_lines: int | None = None,
        kind: str | None = None,
        file_path_pattern: str | None = None,
        limit: int = 50,
    ) -> list:
        rows = self._conn.execute(
            """
            SELECT * FROM nodes
            WHERE line_start IS NOT NULL
              AND line_end IS NOT NULL
              AND (line_end - line_start + 1) >= ?
              AND (? IS NULL OR (line_end - line_start + 1) <= ?)
              AND (? IS NULL OR kind = ?)
              AND (? IS NULL OR file_path LIKE "%" || ? || "%")
            ORDER BY (line_end - line_start + 1) DESC LIMIT ?
            """,
            (
                min_lines,
                max_lines,
                max_lines,
                kind,
                kind,
                file_path_pattern,
                file_path_pattern,
                limit,
            ),
        ).fetchall()
        return [r['name'] for r in rows]

store = Store()

print("Testing search_nodes...")
assert store.search_nodes("foo") == ["foo"]
assert store.search_nodes("foo", kind="Function") == ["foo"]
assert store.search_nodes("foo", kind="Class") == []
assert store.search_nodes("bar") == ["bar"]
# Case insensitive check
assert store.search_nodes("FOO") == ["foo"]
assert store.search_nodes("qn") == ["bar", "foo"]

print("Testing get_nodes_by_size...")
assert store.get_nodes_by_size(min_lines=100) == ["foo"]
assert store.get_nodes_by_size(min_lines=10, max_lines=60) == ["bar"]
assert store.get_nodes_by_size(min_lines=10, kind="Function") == ["foo"]
assert store.get_nodes_by_size(min_lines=10, file_path_pattern="foo") == ["foo"]
assert len(store.get_nodes_by_size(min_lines=1)) == 2

print("All tests passed!")
