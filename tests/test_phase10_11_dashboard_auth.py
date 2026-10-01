"""Phase 10-11 dashboard and GitHub user authentication tests."""

import time


def test_oauth_session_is_signed_and_expiring(monkeypatch):
    monkeypatch.setenv("GITHUB_OAUTH_SESSION_SECRET", "test-secret")
    from app.github_oauth import _sign, _verify
    value = _sign({"sub": 123, "login": "tester", "installations": [7], "exp": int(time.time()) + 60})
    assert _verify(value)["sub"] == 123
    raw, sig = value.rsplit(".", 1)
    assert _verify(raw + "x." + sig) is None


def test_expired_oauth_session_is_rejected(monkeypatch):
    monkeypatch.setenv("GITHUB_OAUTH_SESSION_SECRET", "test-secret")
    from app.github_oauth import _sign, _verify
    value = _sign({"sub": 123, "exp": int(time.time()) - 1})
    assert _verify(value) is None


def test_oauth_finish_does_not_put_access_token_in_session(monkeypatch):
    monkeypatch.setenv("GITHUB_OAUTH_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "secret")
    from app import github_oauth

    def fake_request(method, url, **kwargs):
        class R:
            def raise_for_status(self): pass
            def json(self):
                if url.endswith("/access_token"):
                    return {"access_token": "gho_SECRET"}
                if url.endswith("/user"):
                    return {"id": 42, "login": "elif"}
                return {"installations": [{"id": 99}]}
        return R()

    monkeypatch.setattr(github_oauth.requests, "request", fake_request)
    from types import SimpleNamespace
    state = github_oauth._sign({"state": "abc", "exp": int(time.time()) + 60})
    request = SimpleNamespace(cookies={github_oauth.STATE_COOKIE: state}, base_url="https://example.com/")
    response = github_oauth.finish_login(request, "code", "abc")
    assert "gho_SECRET" not in str(response.headers)
    cookies = [value.decode() for key, value in response.raw_headers if key.lower() == b"set-cookie"]
    session_cookie = next(value for value in cookies if value.startswith("secpr_session="))
    session_value = session_cookie.split("secpr_session=", 1)[1].split(";", 1)[0].strip('"')
    session = github_oauth._verify(session_value)
    assert session["sub"] == 42
    assert session["login"] == "elif"
    assert session["installations"] == [99]


def test_dashboard_query_functions_have_empty_scope(monkeypatch):
    from app import repository
    monkeypatch.setattr(repository, "db_enabled", lambda: True)
    assert repository.get_dashboard_summary([])["total_reviews"] == 0
    assert repository.get_recent_review_runs(20, []) == []
    assert repository.get_review_run_detail(1, []) is None
