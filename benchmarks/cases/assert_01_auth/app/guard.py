def require_admin(user):
    assert user.is_admin, "admin only"
