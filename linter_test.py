import sqlite3
SQL_PART = " AND 1=1"
def test(conn, qn):
    conn.execute("SELECT * FROM nodes WHERE qn = ?" + SQL_PART, (qn,))
