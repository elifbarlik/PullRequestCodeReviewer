"""Phase 10-11 dashboard and GitHub user authentication tests."""

import json
import time


def test_oauth_session_is_signed_and_expiring(monkeypatch):
    monkeypatch.setenv("GITHUB_OAUTH_SESSION_SECRET", "test-secret")
    from app.github_oauth import _sign, _verify

    value = _sign({"sub": 123, "login": "tester", "installations": [7], "exp": int(time.time()) + 60})
    assert _verify(value)["sub"] == 123
    assert _verify(value)["installations"] == [7]

    raw, sig = value.rsplit(".", 1)
    tampered = raw + "x." + sig
    assert _verify(tampered) is None


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

    class Response:
        def raise_for_status(self): pass
        def json(self): return {}

    calls = []
    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
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
    request = SimpleNamespace(
        cookies={},
        base_url="https://example.com/",
    )
    # State verification is exercised separately; this test focuses on the
    # session payload generated after a successful GitHub response.
    state = github_oauth._sign({"state": "abc", "exp": int(time.time()) + 60})
    request.cookies = {github_oauth.STATE_COOKIE: state}
    response = github_oauth.finish_login(request, "code", "abc")
    cookie_headers = str(response.headers)
    assert "gho_SECRET" not in cookie_headers
    assert "99" in cookie_headers


def test_dashboard_query_functions_have_empty_scope(monkeypatch):
    from app import repository
    monkeypatch.setattr(repository, "db_enabled", lambda: True)
    assert repository.get_dashboard_summary([])["total_reviews"] == 0
    assert repository.get_recent_review_runs(20, []) == []
    assert repository.get_review_run_detail(1, []) is None
