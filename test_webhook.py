#!/usr/bin/env python3
"""
GitHub Webhook Test Script

Bu script, webhook endpoint'ini test etmek için kullanılır.
Gerçek bir GitHub webhook payload'u simüle eder ve HMAC signature oluşturur.
"""

import requests
import json
import hmac
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

# Webhook URL (ngrok veya local)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhook")
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "test_secret")

# Sample GitHub PR webhook payload (opened event)
SAMPLE_PAYLOAD = {
    "action": "opened",
    "number": 1,
    "pull_request": {
        "number": 1,
        "state": "open",
        "title": "Test PR",
        "user": {
            "login": "testuser"
        },
        "head": {
            "ref": "feature-branch",
            "sha": "abc123"
        },
        "base": {
            "ref": "main",
            "sha": "def456"
        }
    },
    "repository": {
        "name": "test-repo",
        "full_name": "testuser/test-repo",
        "owner": {
            "login": "testuser"
        }
    },
    "sender": {
        "login": "testuser"
    }
}


def generate_signature(payload: dict, secret: str) -> str:
    """
    GitHub webhook signature oluştur (HMAC SHA-256)

    Args:
        payload: JSON payload
        secret: Webhook secret

    Returns:
        sha256=<signature> formatında string
    """
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode()
    mac = hmac.new(
        secret.encode(),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    )
    return f"sha256={mac.hexdigest()}"


def test_webhook_ping():
    """Basit ping test (signature olmadan)"""
    print("=" * 60)
    print("TEST 1: Ping Testi (Signature Yok)")
    print("=" * 60)

    ping_payload = {
        "zen": "Design for failure.",
        "hook_id": 123456
    }

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "ping"
    }

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=ping_payload,
            headers=headers,
            timeout=10
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 403:
            print("⚠️  Signature doğrulaması çalışıyor (beklendiği gibi)")
        else:
            print("✅ Ping başarılı")

    except Exception as e:
        print(f"❌ Hata: {e}")


def test_webhook_with_signature():
    """PR webhook test (signature ile)"""
    print("\n" + "=" * 60)
    print("TEST 2: PR Webhook Testi (Signature İle)")
    print("=" * 60)

    # Signature oluştur
    signature = generate_signature(SAMPLE_PAYLOAD, WEBHOOK_SECRET)

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": signature
    }

    print(f"\n📤 İstek gönderiliyor: {WEBHOOK_URL}")
    print(f"🔐 Signature: {signature[:30]}...")

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=SAMPLE_PAYLOAD,
            headers=headers,
            timeout=30  # LLM işlemi uzun sürebilir
        )

        print(f"\n📥 Status Code: {response.status_code}")

        if response.status_code == 200:
            print("✅ Webhook başarıyla işlendi!")
            result = response.json()
            print(f"\n📋 Response:")
            print(json.dumps(result, indent=2))
        elif response.status_code == 403:
            print("❌ Signature doğrulaması başarısız!")
            print("⚠️  GITHUB_WEBHOOK_SECRET doğru mu kontrol edin")
        else:
            print(f"⚠️  Beklenmeyen durum kodu: {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.Timeout:
        print("⏱️  Timeout: LLM işlemi uzun sürüyor olabilir")
    except Exception as e:
        print(f"❌ Hata: {e}")


def test_webhook_invalid_signature():
    """Geçersiz signature test"""
    print("\n" + "=" * 60)
    print("TEST 3: Geçersiz Signature Testi")
    print("=" * 60)

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": "sha256=invalid_signature_here"
    }

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=SAMPLE_PAYLOAD,
            headers=headers,
            timeout=10
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 403:
            print("✅ Geçersiz signature reddedildi (güvenlik çalışıyor!)")
        else:
            print("⚠️  Güvenlik açığı: Geçersiz signature kabul edildi!")

    except Exception as e:
        print(f"❌ Hata: {e}")


def test_webhook_ignored_action():
    """İgnore edilmesi gereken action test"""
    print("\n" + "=" * 60)
    print("TEST 4: Ignore Edilmesi Gereken Action")
    print("=" * 60)

    payload = SAMPLE_PAYLOAD.copy()
    payload["action"] = "closed"  # Bu action ignore edilmeli

    signature = generate_signature(payload, WEBHOOK_SECRET)

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": signature
    }

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Response: {result}")

        if result.get("status") == "ignored":
            print("✅ 'closed' action doğru şekilde ignore edildi")
        else:
            print("⚠️  'closed' action işlendi (beklenmeyen)")

    except Exception as e:
        print(f"❌ Hata: {e}")


def interactive_test():
    """Interaktif test modu"""
    print("\n" + "=" * 60)
    print("🧪 GitHub Webhook Test Suite")
    print("=" * 60)

    print(f"\n⚙️  Yapılandırma:")
    print(f"   Webhook URL: {WEBHOOK_URL}")
    print(f"   Secret: {'*' * 20} (gizli)")

    menu = """
Hangi testi çalıştırmak istersiniz?
1. Ping Test (signature yok)
2. PR Webhook (geçerli signature)
3. Geçersiz Signature Test
4. Ignore Action Test
5. Tümünü Çalıştır
0. Çık

Seçim: """

    while True:
        choice = input(menu).strip()

        if choice == "1":
            test_webhook_ping()
        elif choice == "2":
            test_webhook_with_signature()
        elif choice == "3":
            test_webhook_invalid_signature()
        elif choice == "4":
            test_webhook_ignored_action()
        elif choice == "5":
            test_webhook_ping()
            test_webhook_with_signature()
            test_webhook_invalid_signature()
            test_webhook_ignored_action()
            print("\n" + "=" * 60)
            print("✅ Tüm testler tamamlandı!")
            print("=" * 60)
        elif choice == "0":
            print("\n👋 Test suite'den çıkılıyor...")
            break
        else:
            print("❌ Geçersiz seçim")


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║          GitHub Webhook Test Script                       ║
║          PR Code Reviewer                                 ║
╚═══════════════════════════════════════════════════════════╝
""")

    # .env kontrol
    if not os.path.exists(".env"):
        print("⚠️  .env dosyası bulunamadı!")
        print("1. .env.example dosyasını .env olarak kopyalayın")
        print("2. GITHUB_WEBHOOK_SECRET ekleyin")
        exit(1)

    # Uygulamanın çalışıp çalışmadığını kontrol et
    try:
        health_check = requests.get(
            WEBHOOK_URL.replace("/webhook", "/health"),
            timeout=5
        )
        if health_check.status_code == 200:
            print("✅ Uygulama çalışıyor!\n")
        else:
            print("⚠️  Uygulama yanıt vermiyor!")
    except:
        print("❌ Uygulamaya bağlanılamadı!")
        print("uvicorn app.main:app --reload komutunu çalıştırdınız mı?\n")

    interactive_test()
