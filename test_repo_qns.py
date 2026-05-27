import sqlite3
import time

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.execute("CREATE TABLE nodes (qualified_name TEXT, repo_id TEXT)")
conn.execute("BEGIN")
for i in range(100000):
    conn.execute("INSERT INTO nodes VALUES (?, ?)", (f"qn{i}", "repo1"))
conn.execute("COMMIT")


def original(repo):
    start = time.time()
    rows = conn.execute(
        "SELECT qualified_name FROM nodes WHERE repo_id = ?",
        (repo,),
    ).fetchall()
    repo_qns = {r["qualified_name"] for r in rows}
    return time.time() - start, len(repo_qns)


print(original("repo1"))
