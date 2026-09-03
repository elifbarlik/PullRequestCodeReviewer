def get_user(cur, uid):
    cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
    return cur.fetchone()
