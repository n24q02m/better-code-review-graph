import json
import sqlite3
import time
from pathlib import Path

# Create a temporary DB with 10,000 mock rows representing nodes
db_path = Path("benchmark_json.db")
if db_path.exists():
    db_path.unlink()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
conn.execute("CREATE TABLE nodes (id INTEGER, extra TEXT)")

# Insert 10,000 rows where `extra` is largely empty
rows_to_insert = [(i, "{}") for i in range(10000)]
conn.executemany("INSERT INTO nodes (id, extra) VALUES (?, ?)", rows_to_insert)
conn.commit()

def test_original():
    cursor = conn.execute("SELECT * FROM nodes")
    start = time.time()
    for row in cursor:
        extra_val = row["extra"]
        _ = json.loads(extra_val) if extra_val else {}
    return time.time() - start

def test_optimized():
    cursor = conn.execute("SELECT * FROM nodes")
    start = time.time()
    for row in cursor:
        extra_val = row["extra"]
        _ = {} if not extra_val or extra_val == "{}" else json.loads(extra_val)
    return time.time() - start

# Warm up
test_original()
test_optimized()

# Run the benchmark
n_iters = 5
orig_time = sum(test_original() for _ in range(n_iters)) / n_iters
opt_time = sum(test_optimized() for _ in range(n_iters)) / n_iters

print(f"Original average: {orig_time:.6f}s")
print(f"Optimized average: {opt_time:.6f}s")
print(f"Improvement: {(orig_time - opt_time) / orig_time * 100:.2f}%")

db_path.unlink()
