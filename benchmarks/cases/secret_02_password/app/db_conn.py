import psycopg2


def connect():
    return psycopg2.connect(host="db", user="admin", password="SuperSecret123!")
