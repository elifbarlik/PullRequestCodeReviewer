"""
SecPR-TR — GitHub App ana uygulama modülü.

Webhook event'leri:
  - pull_request (opened / synchronize)  → güvenlik analizi + PR yorumu
  - installation (created / deleted)      → kurulum kaydı log'u (Faz 2'de DB'ye yazılacak)
  - installation_repositories             → repo ekleme/çıkarma log'u

Kimlik doğrulama:
  - Webhook imzası: HMAC SHA-256 (GITHUB_WEBHOOK_SECRET)  — secret zorunlu
  - API çağrıları: JWT → installation access token        — GitHub App flow
"""

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from app.reviewer import review_diff, truncate_diff, ParseStatistics
from app.github_client import GitHubAppClient
import json
import hmac
import hashlib
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SecPR-TR", version="0.3.0")


# -------------------------------------------------------------------
# Webhook imza doğrulama
# -------------------------------------------------------------------

def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    GitHub webhook HMAC SHA-256 imzasını doğrular.

    Secret tanımlı değilse kesinlikle False döner — multi-tenant bir
    uygulamada secret olmadan webhook kabul etmek kabul edilemez bir
    güvenlik açığıdır.

    Args:
        payload_body: Ham request body (bytes)
        signature_header: X-Hub-Signature-256 header değeri

    Returns:
        True: İmza geçerli | False: Geçersiz veya secret eksik
    """
    if not signature_header:
        return False

    # Secret yoksa reddet — production'da her zaman zorunlu
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("❌ GITHUB_WEBHOOK_SECRET tanımlanmamış — webhook reddedildi")
        return False

    # Beklenen format: sha256=<hexdigest>
    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header.split("=", 1)[1]
    mac = hmac.new(webhook_secret.encode(), msg=payload_body, digestmod=hashlib.sha256)
    calculated_signature = mac.hexdigest()

    # Timing attack'a karşı sabit zamanlı karşılaştırma
    return hmac.compare_digest(calculated_signature, expected_signature)


# -------------------------------------------------------------------
# Request / Response modelleri
# -------------------------------------------------------------------

class DiffRequest(BaseModel):
    diff_text: str
    file_name: Optional[str] = None
    review_types: Optional[List[str]] = ["short_summary", "bug_detection"]


class ReviewResponse(BaseModel):
    status: str
    file_name: Optional[str] = None
    diff_length: int
    was_truncated: bool
    analyses: dict
    metadata: Optional[dict] = None


# -------------------------------------------------------------------
# Endpoint: sağlık kontrolü
# -------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "version": "0.3.0", "app": "SecPR-TR"}


# -------------------------------------------------------------------
# Endpoint: istatistikler
# -------------------------------------------------------------------

@app.get("/stats")
async def get_stats():
    """JSON parser istatistiklerini döndürür"""
    return {
        "total_attempts": ParseStatistics.total_attempts,
        "successful": ParseStatistics.successful_parses,
        "failed": ParseStatistics.failed_parses,
        "success_rate": f"{ParseStatistics.get_success_rate():.1f}%",
    }


# -------------------------------------------------------------------
# Endpoint: yerel diff analizi (manuel test için)
# -------------------------------------------------------------------

@app.post("/local-review", response_model=ReviewResponse)
async def local_review(request: DiffRequest):
    """Doğrudan gönderilen diff'i analiz eder (webhook gerektirmez)."""

    if not request.diff_text or len(request.diff_text.strip()) == 0:
        raise HTTPException(status_code=400, detail="diff_text boş olamaz")

    original_size = len(request.diff_text)
    diff_to_analyze = truncate_diff(request.diff_text, max_length=3000)
    was_truncated = len(diff_to_analyze) < original_size

    valid_types = ["short_summary", "bug_detection", "performance", "security"]
    review_types = request.review_types or ["short_summary", "bug_detection"]

    for rt in review_types:
        if rt not in valid_types:
            raise HTTPException(status_code=400, detail=f"Geçersiz review_type: {rt}")

    try:
        result = review_diff(diff_text=diff_to_analyze, review_types=review_types)
        ParseStatistics.record_attempt(result["status"] == "success")
    except Exception as e:
        logger.error(f"Review hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Review hatası: {str(e)}")

    return ReviewResponse(
        status=result["status"],
        file_name=request.file_name,
        diff_length=original_size,
        was_truncated=was_truncated,
        analyses=result["analyses"],
        metadata=result.get("metadata"),
    )


# -------------------------------------------------------------------
# İç yardımcı: PR analizi ve yorum gönderme
# -------------------------------------------------------------------

async def _run_pr_review(
    installation_id: int,
    owner: str,
    repo: str,
    pr_number: int,
    review_types: Optional[List[str]] = None,
) -> dict:
    """
    Verilen PR'yi analiz eder ve sonuçları PR'e yorum olarak gönderir.

    Args:
        installation_id: Webhook'tan gelen installation.id
        owner, repo, pr_number: PR koordinatları
        review_types: Hangi analizler çalışsın

    Returns:
        Sonuç özeti dict'i
    """
    if review_types is None:
        review_types = ["short_summary", "security"]

    # Installation'a özgü client — kendi installation token'ını yönetir
    client = GitHubAppClient(installation_id=installation_id)

    logger.info(f"📥 Diff alınıyor: {owner}/{repo}#{pr_number}")
    diff_text = client.get_pr_diff(owner=owner, repo=repo, pr_number=pr_number)

    if not diff_text or not diff_text.strip():
        raise ValueError("PR diff'i boş")

    original_size = len(diff_text)
    diff_to_analyze = truncate_diff(diff_text)
    was_truncated = len(diff_to_analyze) < original_size

    logger.info(f"🔍 Analiz başlıyor: {review_types}")
    result = review_diff(diff_text=diff_to_analyze, review_types=review_types)
    ParseStatistics.record_attempt(result["status"] == "success")

    comment_body = _format_review_comment(result, was_truncated)

    logger.info("💬 PR'e yorum gönderiliyor...")
    client.post_pr_comment(owner=owner, repo=repo, pr_number=pr_number, body=comment_body)

    return {
        "status": "success",
        "message": f"PR #{pr_number} incelendi",
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "diff_size": original_size,
        "was_truncated": was_truncated,
        "analyses": result["analyses"],
    }


# -------------------------------------------------------------------
# Webhook ana endpoint
# -------------------------------------------------------------------

@app.post("/webhook")
async def github_webhook(request: Request):
    """
    GitHub App webhook endpoint'i.

    İşlenen event'ler:
      - pull_request / opened, synchronize  → PR analizi
      - installation / created, deleted     → kurulum logu (Faz 2: DB kaydı)
      - installation_repositories           → repo değişikliği logu
    """
    try:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")

        if not verify_github_signature(body, signature):
            logger.error("❌ Geçersiz webhook imzası")
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = json.loads(body)
        event_type = request.headers.get("X-GitHub-Event", "")
        action = payload.get("action", "")

        logger.info(f"🔔 Webhook: event={event_type} action={action}")

        # ── installation event'leri ──────────────────────────────────
        if event_type == "installation":
            return await _handle_installation_event(action, payload)

        # ── installation_repositories event'leri ────────────────────
        if event_type == "installation_repositories":
            return await _handle_installation_repositories_event(action, payload)

        # ── pull_request event'leri ──────────────────────────────────
        if event_type == "pull_request":
            return await _handle_pull_request_event(action, payload)

        # Diğer event'leri görmezden gel
        return {"status": "ignored", "reason": f"'{event_type}' event'i desteklenmiyor"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Webhook hatası: {str(e)}")
        return {"status": "error", "message": str(e)}


# -------------------------------------------------------------------
# Event handler'ları
# -------------------------------------------------------------------

async def _handle_installation_event(action: str, payload: dict) -> dict:
    """
    GitHub App installation event'ini işler.

    created  → yeni kurulum (Faz 2'de installations tablosuna yazılacak)
    deleted  → kaldırıldı   (Faz 2'de soft-delete yapılacak)
    """
    installation = payload.get("installation", {})
    installation_id = installation.get("id")
    account = installation.get("account", {})
    account_login = account.get("login", "unknown")
    account_type = account.get("type", "unknown")  # "User" veya "Organization"

    if action == "created":
        logger.info(
            f"🎉 Yeni kurulum: installation_id={installation_id} "
            f"hesap={account_login} ({account_type})"
        )
        # TODO (Faz 2): installations tablosuna kaydet
        #   db.installations.insert(installation_id, account_login, account_type, ...)
        return {
            "status": "ok",
            "event": "installation.created",
            "installation_id": installation_id,
            "account": account_login,
        }

    elif action == "deleted":
        logger.info(
            f"🗑️  Kurulum kaldırıldı: installation_id={installation_id} "
            f"hesap={account_login}"
        )
        # TODO (Faz 2): installations tablosunda is_active=False yap
        return {
            "status": "ok",
            "event": "installation.deleted",
            "installation_id": installation_id,
            "account": account_login,
        }

    return {"status": "ignored", "reason": f"installation.{action} işlenmiyor"}


async def _handle_installation_repositories_event(action: str, payload: dict) -> dict:
    """
    Repo ekleme/çıkarma event'lerini loglar.

    added   → kullanıcı yeni repoya erişim verdi
    removed → kullanıcı repodan erişimi kaldırdı
    """
    installation_id = payload.get("installation", {}).get("id")
    repos_added = [r["full_name"] for r in payload.get("repositories_added", [])]
    repos_removed = [r["full_name"] for r in payload.get("repositories_removed", [])]

    if repos_added:
        logger.info(f"➕ Repo eklendi — installation={installation_id}: {repos_added}")
    if repos_removed:
        logger.info(f"➖ Repo çıkarıldı — installation={installation_id}: {repos_removed}")

    # TODO (Faz 2): repo erişim listesini DB'de güncelle
    return {
        "status": "ok",
        "event": f"installation_repositories.{action}",
        "installation_id": installation_id,
        "repos_added": repos_added,
        "repos_removed": repos_removed,
    }


async def _handle_pull_request_event(action: str, payload: dict) -> dict:
    """
    Pull request event'ini işler.

    opened / synchronize → analiz tetikler
    Diğer action'lar    → görmezden gelinir
    """
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored", "reason": f"pull_request.{action} analiz tetiklemez"}

    pr = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})
    installation = payload.get("installation", {})

    owner = repo_data.get("owner", {}).get("login")
    repo = repo_data.get("name")
    pr_number = pr.get("number")
    installation_id = installation.get("id")

    if not all([owner, repo, pr_number, installation_id]):
        missing = [k for k, v in {
            "owner": owner, "repo": repo,
            "pr_number": pr_number, "installation_id": installation_id
        }.items() if not v]
        raise ValueError(f"Webhook payload'ında eksik alan: {missing}")

    logger.info(f"🔔 PR event: {owner}/{repo}#{pr_number} action={action} installation={installation_id}")

    return await _run_pr_review(
        installation_id=installation_id,
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        review_types=["short_summary", "security"],
    )


# -------------------------------------------------------------------
# Yorum formatlama
# -------------------------------------------------------------------

def _format_review_comment(result: dict, was_truncated: bool = False) -> str:
    """Review sonuçlarını GitHub PR yorumu olarak formatlar."""

    comment = "## 🔒 SecPR-TR — Güvenlik Analizi\n\n"

    if was_truncated:
        comment += "⚠️ **Not:** Diff çok büyük olduğu için kısaltıldı. Analiz kısmi olabilir.\n\n"

    analyses = result.get("analyses", {})

    # Özet
    if "short_summary" in analyses:
        summary = analyses["short_summary"]
        if isinstance(summary, dict) and "error" not in summary:
            comment += "### 📝 Özet\n"
            comment += f"**Değişiklik:** {summary.get('summary', 'N/A')}\n"
            comment += f"**Önem:** {summary.get('severity', 'N/A')}\n"
            comment += f"**Tip:** {summary.get('type', 'N/A')}\n\n"

    # Güvenlik
    if "security" in analyses:
        security = analyses["security"]
        if isinstance(security, dict) and "error" not in security:
            if security.get("has_security_issues"):
                comment += "### 🚨 Güvenlik Bulguları\n"
                for vuln in security.get("vulnerabilities", []):
                    comment += f"\n**⚠️ {vuln.get('file', 'bilinmiyor')}:{vuln.get('line', '?')}**\n"
                    comment += f"- **Risk:** {vuln.get('risk', 'bilinmiyor')}\n"
                    comment += f"- **Açıklama:** {vuln.get('description', 'N/A')}\n"
                    comment += f"- **Öneri:** {vuln.get('recommendation', 'N/A')}\n"
                comment += f"\n**Güvenlik Seviyesi:** {security.get('security_level', 'safe')}\n\n"
            else:
                comment += "### ✅ Güvenlik Kontrolü\n"
                comment += f"Güvenlik açığı tespit edilmedi. Seviye: **{security.get('security_level', 'safe')}**\n\n"

    # Hata tespiti (varsa)
    if "bug_detection" in analyses:
        bugs = analyses["bug_detection"]
        if isinstance(bugs, dict) and "error" not in bugs:
            if bugs.get("has_bugs"):
                comment += "### 🐛 Tespit Edilen Hatalar\n"
                for issue in bugs.get("issues", []):
                    comment += f"\n**📍 {issue.get('file', 'bilinmiyor')}:{issue.get('line', '?')}**\n"
                    comment += f"- **Önem:** {issue.get('severity', 'bilinmiyor')}\n"
                    comment += f"- **Tanım:** {issue.get('description', 'N/A')}\n"
                    comment += f"- **Öneri:** {issue.get('suggestion', 'N/A')}\n"
                comment += f"\n**Genel Risk:** {bugs.get('overall_risk', 'düşük')}\n\n"

    # Footer
    comment += "\n---\n"
    comment += "*🔒 [SecPR-TR](https://github.com/elifbarlik/PullRequestCodeReviewer) tarafından otomatik oluşturulmuştur.*"

    return comment
