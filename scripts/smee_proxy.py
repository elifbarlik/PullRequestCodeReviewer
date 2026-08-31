"""
smee.io webhook proxy — yerel geliştirme için.

smee.io'dan SSE stream açar, gelen webhook'ları
localhost:8000/webhook'a iletir.

Kullanım:
    python scripts/smee_proxy.py <smee_url>

Örnek:
    python scripts/smee_proxy.py https://smee.io/secpr-tr-dev-abc123
"""

import sys
import json
import requests
import sseclient
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("smee")

LOCAL_URL = "http://localhost:8000/webhook"


def forward(smee_url: str):
    log.info(f"smee.io bağlanıyor: {smee_url}")
    log.info(f"Hedef: {LOCAL_URL}")
    log.info("Webhook bekleniyor... (Ctrl+C ile durdur)\n")

    headers = {"Accept": "text/event-stream"}
    response = requests.get(smee_url, stream=True, headers=headers)
    client = sseclient.SSEClient(response)

    for event in client.events():
        if event.event == "message" and event.data and event.data != "{}":
            try:
                data = json.loads(event.data)
                # smee.io body ve header'ları birlikte gönderir
                body = data.get("body", data)
                forward_headers = {
                    k: v for k, v in data.items()
                    if k.startswith("x-github") or k.startswith("x-hub") or k == "content-type"
                }
                forward_headers.setdefault("content-type", "application/json")

                log.info(f"→ Webhook iletiliyor: {forward_headers.get('x-github-event', '?')} "
                         f"/ {body.get('action', '?') if isinstance(body, dict) else '?'}")

                resp = requests.post(
                    LOCAL_URL,
                    json=body,
                    headers=forward_headers,
                    timeout=30,
                )
                log.info(f"← Yanıt: {resp.status_code} — {resp.text[:120]}")
            except Exception as e:
                log.error(f"İletme hatası: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python scripts/smee_proxy.py <smee_url>")
        print("Örnek:    python scripts/smee_proxy.py https://smee.io/secpr-tr-dev-abc123")
        sys.exit(1)
    forward(sys.argv[1])
