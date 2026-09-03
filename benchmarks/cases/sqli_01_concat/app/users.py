import sqlite3


def get_user(conn, uid):
    cur = conn.cursor()
    query = "SELECT * FROM users WHERE id = " + str(uid)
    cur.execute(query)
    return cur.fetchone()
