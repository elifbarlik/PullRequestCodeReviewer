import hashlib


def hash_pw(pw, salt):
    return hashlib.md5(pw.encode()).hexdigest()
