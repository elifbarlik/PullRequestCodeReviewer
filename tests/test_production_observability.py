"""Phase 4 production observability smoke tests."""

from fastapi.testclient import TestClient

from app import main


def test_health_reports_sentry_state(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setenv("GITHUB_APP_ID", "smoke-test")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "smoke-test-key")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "smoke-webhook-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "smoke-gemini-key")
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert "sentry" in response.json()["checks"]


def test_sentry_smoke_endpoint_requires_admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "admin-secret")
    response = TestClient(main.app).post("/admin/sentry-test")
    assert response.status_code == 401


def test_sentry_smoke_endpoint_reports_missing_dsn(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "admin-secret")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    response = TestClient(main.app).post(
        "/admin/sentry-test", headers={"X-Admin-Token": "admin-secret"}
    )
    assert response.status_code == 503
    assert "SENTRY_DSN" in response.json()["detail"]
