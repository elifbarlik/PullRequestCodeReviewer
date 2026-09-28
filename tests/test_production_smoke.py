"""
Phase 1 production smoke tests.

These tests exercise the public surface that must survive packaging:
landing page, dashboard, docs, health metadata, and webhook rejection.
They do not call GitHub or Gemini.
"""

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def smoke_client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GITHUB_APP_ID", "smoke-test")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "smoke-test-key")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "smoke-webhook-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "smoke-gemini-key")
    return TestClient(main.app)


def test_health_contract(smoke_client):
    response = smoke_client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["app"] == "SecPR-TR"
    assert body["version"] == main.APP_VERSION
    assert body["status"] in {"ok", "degraded"}
    assert set(body["checks"]) >= {"database", "semgrep", "github", "gemini", "webhook"}
    assert body["checks"]["database"] == "disabled"
    assert body["checks"]["github"] == "configured"
    assert body["checks"]["gemini"] == "configured"
    assert body["checks"]["webhook"] == "configured"


@pytest.mark.parametrize(
    "path, expected_marker",
    [
        ("/", "SecPR-TR"),
        ("/dashboard", "SecPR-TR"),
        ("/docs", "SecPR-TR"),
    ],
)
def test_public_pages_are_served(smoke_client, path, expected_marker):
    response = smoke_client.get(path)
    assert response.status_code == 200
    assert expected_marker in response.text


def test_webhook_requires_valid_signature(smoke_client):
    response = smoke_client.post(
        "/webhook",
        content=b"{}",
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "phase1-smoke",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )
    assert response.status_code == 403


def test_metrics_endpoint(smoke_client):
    response = smoke_client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "parser_success_rate_pct" in body
    assert "usage" in body
    usage = body["usage"]
    if usage:
        assert "p50_duration_ms_24h" in usage
        assert "p95_duration_ms_24h" in usage
        assert "avg_timing_ms_24h" in usage
        assert "semgrep_unavailable_rate_pct_24h" in usage
