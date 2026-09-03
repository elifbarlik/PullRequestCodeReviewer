def fetch(cur, name):
    cur.execute("SELECT * FROM report WHERE owner = '%s'" % name)
    return cur.fetchall()
