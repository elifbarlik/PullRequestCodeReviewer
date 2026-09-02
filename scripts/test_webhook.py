"""
Webhook simülasyonu — smee olmadan direkt test.

Gerçek bir GitHub pull_request webhook payload'ı üretir ve
localhost:8000/webhook'a gönderir. HMAC imzasını da doğru hesaplar.

Kullanım:
    python scripts/test_webhook.py <owner> <repo> <pr_number> <installation_id>

Örnek:
    python scripts/test_webhook.py elifbarlik test-repo 1 12345678
"""

import sys
import json
import hmac
import hashlib
import requests
import os
from dotenv import load_dotenv

load_dotenv()

LOCAL_URL = "http://localhost:8000/webhook"


def make_payload(owner: str, repo: str, pr_number: int, installation_id: int) -> dict:
    return {
        "action": "opened",
        "number": pr_number,
        "pull_request": {
            "number": pr_number,
            "title": "Test PR",
            "body": "Webhook simülasyon testi",
            "state": "open",
            "head": {"sha": "abc1234def5678"},
            "base": {"ref": "main"},
        },
        "repository": {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "owner": {"login": owner},
        },
        "installation": {
            "id": installation_id,
        },
    }


def sign(payload_bytes: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), msg=payload_bytes, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def send(owner: str, repo: str, pr_number: int, installation_id: int):
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        print("HATA: GITHUB_WEBHOOK_SECRET .env'de yok")
        sys.exit(1)

    payload = make_payload(owner, repo, pr_number, installation_id)
    body = json.dumps(payload).encode()
    signature = sign(body, secret)

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": signature,
        "X-GitHub-Delivery": "test-delivery-001",
    }

    print(f"→ Gönderiliyor: {owner}/{repo}#{pr_number} (installation={installation_id})")
    print(f"  URL: {LOCAL_URL}")
    print(f"  İmza: {signature[:30]}...")

    try:
        resp = requests.post(LOCAL_URL, data=body, headers=headers, timeout=60)
        print(f"\n← Yanıt: HTTP {resp.status_code}")
        try:
            result = resp.json()
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception:
            print(resp.text)
    except requests.exceptions.ConnectionError:
        print("\nHATA: localhost:8000 bağlantısı reddedildi — FastAPI çalışıyor mu?")
    except requests.exceptions.Timeout:
        print("\nZaman aşımı (60s) — Gemini API çok uzun sürdü veya hata var")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Kullanım: python scripts/test_webhook.py <owner> <repo> <pr_number> <installation_id>")
        print()
        print("installation_id'yi bulmak için:")
        print("  python scripts/get_installation_id.py")
        sys.exit(1)

    owner = sys.argv[1]
    repo = sys.argv[2]
    pr_number = int(sys.argv[3])
    installation_id = int(sys.argv[4])

    send(owner, repo, pr_number, installation_id)
