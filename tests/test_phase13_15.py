"""Phase 13-15 settings, observability and error handling tests."""

import time
from types import SimpleNamespace


def _session_cookie(monkeypatch, installations):
    monkeypatch.setenv("GITHUB_OAUTH_SESSION_SECRET", "test-secret")
    from app.github_oauth import _sign
    return _sign({
        "sub": 42,
        "login": "elif",
        "installations": installations,
        "exp": int(time.time()) + 60,
    })


def test_installation_settings_are_user_scoped(monkeypatch):
    monkeypatch.setenv("GITHUB_OAUTH_SESSION_SECRET", "test-secret")
    from app import main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "get_installation_settings", lambda installation_id: {
        "enabled": True, "semgrep_configs": None
    })
    monkeypatch.setattr(main, "set_installation_settings", lambda **kwargs: {
        "enabled": kwargs.get("enabled", True), "semgrep_configs": None
    })
    monkeypatch.setattr("app.db.db_enabled", lambda: True)

    client = TestClient(main.app)
    client.cookies.set("secpr_session", _session_cookie(monkeypatch, [99]))

    assert client.get("/installations/99/settings").status_code == 200
    assert client.get("/installations/100/settings").status_code == 404
    assert client.put("/installations/100/settings", json={"enabled": False}).status_code == 404


def test_metrics_requires_authenticated_installation_scope(monkeypatch):
    monkeypatch.setenv("GITHUB_OAUTH_SESSION_SECRET", "test-secret")
    from app import main
    from fastapi.testclient import TestClient

    captured = {}
    monkeypatch.setattr(main, "get_detailed_metrics", lambda installation_ids=None: captured.setdefault("ids", installation_ids) or {})
    client = TestClient(main.app)

    assert client.get("/metrics").status_code == 401
    client.cookies.set("secpr_session", _session_cookie(monkeypatch, [7, 8]))
    assert client.get("/metrics").status_code == 200
    assert captured["ids"] == [7, 8]


def test_unexpected_errors_return_sanitized_response(monkeypatch):
    from app import main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "get_dashboard_summary", lambda _ids: (_ for _ in ()).throw(RuntimeError("secret-db-password")))
    client = TestClient(main.app)
    client.cookies.set("secpr_session", _session_cookie(monkeypatch, [7]))
    response = client.get("/dashboard/api/summary")
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "secret-db-password" not in response.text
    assert response.headers["X-Request-ID"]
