import tempfile


def scratch():
    path = tempfile.mktemp()
    return path
