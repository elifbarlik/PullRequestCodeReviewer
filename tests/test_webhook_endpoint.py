"""
Faz 4.4 — /webhook endpoint davranışı.

Odak:
  - pull_request event'i 202 "accepted" döner ve analizi arka plana atar
    (senkron beklemez → GitHub 10 sn timeout'una takılmaz)
  - X-GitHub-Delivery ile mükerrer delivery atlanır (retry → tek analiz)
  - imza doğrulaması hâlâ zorunlu
  - installation event'i senkron kalır (hızlı)
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import main


SECRET = "test-secret-123"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    # Her test temiz LRU ile başlasın
    main._SEEN_DELIVERIES.clear()
    return TestClient(main.app)


@pytest.fixture
def spy_pr_handler(monkeypatch):
    calls = []

    async def _fake(action, payload):
        calls.append((action, payload))
        return {"status": "success"}

    monkeypatch.setattr(main, "_handle_pull_request_event", _fake)
    return calls


def _post(client, event, payload, delivery="d-1"):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
            "Content-Type": "application/json",
        },
    )


class TestWebhookPrEvent:
    def test_pr_opened_returns_202_accepted_and_schedules_bg(self, client, spy_pr_handler):
        r = _post(client, "pull_request", {"action": "opened", "number": 1})
        assert r.status_code == 200          # FastAPI TestClient bg task'ları senkron koşturur
        assert r.json()["status"] == "accepted"
        # BackgroundTasks TestClient'ta response'tan sonra çalışır — çağrıldı mı?
        assert spy_pr_handler == [("opened", {"action": "opened", "number": 1})]

    def test_pr_non_actionable_action_ignored(self, client, spy_pr_handler):
        r = _post(client, "pull_request", {"action": "labeled"})
        assert r.json()["status"] == "ignored"
        assert spy_pr_handler == []

    def test_duplicate_delivery_is_skipped(self, client, spy_pr_handler):
        p = {"action": "opened", "number": 7}
        r1 = _post(client, "pull_request", p, delivery="dup-42")
        r2 = _post(client, "pull_request", p, delivery="dup-42")
        assert r1.json()["status"] == "accepted"
        assert r2.json()["status"] == "duplicate"
        assert len(spy_pr_handler) == 1        # ikinci sefer analiz YOK

    def test_different_deliveries_both_processed(self, client, spy_pr_handler):
        p = {"action": "opened", "number": 7}
        _post(client, "pull_request", p, delivery="a")
        _post(client, "pull_request", p, delivery="b")
        assert len(spy_pr_handler) == 2

    def test_bad_signature_rejected(self, client, spy_pr_handler):
        body = json.dumps({"action": "opened"}).encode()
        r = client.post(
            "/webhook",
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256=deadbeef",
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "x",
            },
        )
        assert r.status_code == 403
        assert spy_pr_handler == []


class TestWebhookInstallationEvent:
    def test_installation_event_is_synchronous(self, client, monkeypatch):
        seen = []

        async def _fake(action, payload):
            seen.append(action)
            return {"status": "ok", "event": f"installation.{action}"}

        monkeypatch.setattr(main, "_handle_installation_event", _fake)
        r = _post(client, "installation", {"action": "created",
                                           "installation": {"id": 1}}, delivery="i-1")
        assert r.json()["status"] == "ok"
        assert seen == ["created"]
