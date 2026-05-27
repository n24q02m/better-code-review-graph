import sqlite3

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row

conn.execute("""
CREATE TABLE nodes (
    id TEXT,
    qualified_name TEXT,
    name TEXT,
    kind TEXT,
    file_path TEXT,
    line_start INTEGER,
    line_end INTEGER,
    language TEXT,
    is_test BOOLEAN,
    parent_name TEXT,
    repo_id TEXT,
    valid_from_sha TEXT,
    valid_to_sha TEXT
)
""")

conn.execute("""
INSERT INTO nodes VALUES (
    'id1', 'qname', 'name', 'kind', 'path', 1, 2, 'python', 0, 'parent', 'repo', 'sha1', 'sha2'
)
""")

rows = conn.execute("SELECT * FROM nodes").fetchall()


def slow_way(rows):
    return [dict(r) for r in rows]


def dict_way(rows):
    return [{k: r[k] for k in r.keys()} for r in rows]


import time

start = time.time()
for _ in range(100000):
    slow_way(rows)
print(f"slow: {time.time() - start:.4f}s")

start = time.time()
for _ in range(100000):
    dict_way(rows)
print(f"dict: {time.time() - start:.4f}s")
