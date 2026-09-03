import jwt


def read(token, key):
    return jwt.decode(token, options={"verify_signature": False})
