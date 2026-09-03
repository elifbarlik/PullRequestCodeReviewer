import hashlib


def checksum(data):
    return hashlib.sha256(data).hexdigest()
