import json
import sqlite3
import time

conn = sqlite3.connect(":memory:")
conn.execute(
    "CREATE TABLE edges (source_qualified TEXT, target_qualified TEXT, kind TEXT, file_path TEXT)"
)
conn.execute("BEGIN")
for i in range(1000):
    conn.execute(
        "INSERT INTO edges VALUES (?, ?, ?, ?)",
        (f"src{i}", f"tgt{i}", "CALLS", f"file{i}"),
    )
conn.execute("COMMIT")

qns = [f"src{i}" for i in range(500)]


def original(qns):
    start = time.time()
    rows = conn.execute(
        "SELECT * FROM edges WHERE source_qualified IN (SELECT value FROM json_each(?))",
        (json.dumps(qns),),
    ).fetchall()
    return time.time() - start


def in_clause(qns):
    start = time.time()
    placeholders = ",".join(["?"] * len(qns))
    rows = conn.execute(
        f"SELECT * FROM edges WHERE source_qualified IN ({placeholders})", qns
    ).fetchall()
    return time.time() - start


print("json_each:", original(qns))
print("in_clause:", in_clause(qns))
