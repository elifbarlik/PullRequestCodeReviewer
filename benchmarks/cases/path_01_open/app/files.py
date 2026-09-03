import os

BASE = "/srv/data"


def read_doc(name):
    with open(BASE + "/" + name) as f:
        return f.read()
