from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from app.reviewer import review_diff, truncate_diff, ParseStatistics
from app.github_client import GitHubClient
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

app = FastAPI(title="PR Code Reviewer", version="0.2.0")


def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    GitHub webhook signature'ını doğrula (HMAC SHA-256)

    Args:
        payload_body: Ham request body (bytes)
        signature_header: X-Hub-Signature-256 header değeri

    Returns:
        True: Signature geçerli, False: Geçersiz
    """
    if not signature_header:
        return False

    # GitHub webhook secret'ı al — tanımlı değilse webhook'u reddet
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("❌ GITHUB_WEBHOOK_SECRET tanımlanmamış — webhook reddedildi")
        return False

    # Signature formatı: sha256=<hash>
    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header.split("=")[1]

    # HMAC hesapla
    mac = hmac.new(webhook_secret.encode(), msg=payload_body, digestmod=hashlib.sha256)
    calculated_signature = mac.hexdigest()

    # Timing attack'a karşı secure comparison
    return hmac.compare_digest(calculated_signature, expected_signature)


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


class GitHubReviewRequest(BaseModel):
    """GitHub PR otomatik review isteği"""

    owner: str
    repo: str
    pr_number: int
    review_types: Optional[List[str]] = ["short_summary", "bug_detection"]


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "version": "0.2.0"}


@app.get("/stats")
async def get_stats():
    """Get parser statistics"""
    return {
        "total_attempts": ParseStatistics.total_attempts,
        "successful": ParseStatistics.successful_parses,
        "failed": ParseStatistics.failed_parses,
        "success_rate": f"{ParseStatistics.get_success_rate():.1f}%",
    }


@app.post("/local-review", response_model=ReviewResponse)
async def local_review(request: DiffRequest):
    """Local diff'i analiz et (manuel)"""

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

        # Track parse success
        success = result["status"] == "success"
        ParseStatistics.record_attempt(success)

    except Exception as e:
        logger.error(f"Review error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Review hatası: {str(e)}")

    return ReviewResponse(
        status=result["status"],
        file_name=request.file_name,
        diff_length=original_size,
        was_truncated=was_truncated,
        analyses=result["analyses"],
        metadata=result.get("metadata"),
    )


@app.post("/github-review")
async def github_review(request: GitHubReviewRequest):
    """
    GitHub PR'den diff al, analiz et, sonuçları PR'ye comment olarak gönder
    """

    try:
        # GitHub Client'ı initialize et
        github_client = GitHubClient()

        # PR'den diff'i al
        logger.info(
            f"📥 PR'den diff alınıyor: {request.owner}/{request.repo}#{request.pr_number}"
        )
        diff_text = github_client.get_pr_diff(
            owner=request.owner, repo=request.repo, pr_number=request.pr_number
        )

        if not diff_text or len(diff_text.strip()) == 0:
            raise HTTPException(status_code=400, detail="PR diff'i boş")

        # Diff'i kırp
        original_size = len(diff_text)
        diff_to_analyze = truncate_diff(diff_text)
        was_truncated = len(diff_to_analyze) < original_size

        # Review yap (two-stage)
        logger.info(f"🔍 Analiz yapılıyor: {request.review_types}")
        result = review_diff(
            diff_text=diff_to_analyze,
            review_types=request.review_types or ["short_summary", "bug_detection"],
        )

        # Track parse success
        ParseStatistics.record_attempt(result["status"] == "success")

        # Sonuçları PR'e comment olarak gönder
        comment_body = _format_review_comment(result, was_truncated)

        logger.info(f"💬 Comment gönderiliyor PR'ye...")
        github_client.post_pr_comment(
            owner=request.owner,
            repo=request.repo,
            pr_number=request.pr_number,
            body=comment_body,
        )

        return {
            "status": "success",
            "message": f"PR #{request.pr_number} review tamamlandı",
            "owner": request.owner,
            "repo": request.repo,
            "pr_number": request.pr_number,
            "diff_size": original_size,
            "was_truncated": was_truncated,
            "analyses": result["analyses"],
            "metadata": result.get("metadata"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GitHub review error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Review hatası: {str(e)}")


def _format_review_comment(result: dict, was_truncated: bool = False) -> str:
    """Format review results as GitHub comment"""

    comment = "## 🤖 PR Code Reviewer - Otomatik Analiz\n\n"

    # Add truncation warning
    if was_truncated:
        comment += "⚠️ **Not:** Diff çok büyük olduğu için kısaltıldı. Analiz kısmi olabilir.\n\n"

    analyses = result.get("analyses", {})

    # Short Summary
    if "short_summary" in analyses:
        summary = analyses["short_summary"]
        if isinstance(summary, dict) and "error" not in summary:
            comment += f"### 📝 Özet\n"
            comment += f"**Değişiklik:** {summary.get('summary', 'N/A')}\n"
            comment += f"**Önem:** {summary.get('severity', 'N/A')}\n"
            comment += f"**Tip:** {summary.get('type', 'N/A')}\n\n"

    # Bug Detection
    if "bug_detection" in analyses:
        bugs = analyses["bug_detection"]
        if isinstance(bugs, dict) and "error" not in bugs:
            if bugs.get("has_bugs"):
                comment += f"### 🐛 Bulunan Hatalar\n"
                for issue in bugs.get("issues", []):
                    comment += f"\n**📍 {issue.get('file', 'unknown')}:{issue.get('line', '?')}**\n"
                    comment += f"- **Önem:** {issue.get('severity', 'unknown')}\n"
                    comment += f"- **Tanım:** {issue.get('description', 'N/A')}\n"
                    comment += f"- **Öneri:** {issue.get('suggestion', 'N/A')}\n"
                comment += f"\n**Genel Risk:** {bugs.get('overall_risk', 'low')}\n\n"
            else:
                comment += f"### ✅ Hata Bulunmadı\n"
                comment += f"**Risk Seviyesi:** {bugs.get('overall_risk', 'low')}\n\n"

    # Security Review
    if "security" in analyses:
        security = analyses["security"]
        if isinstance(security, dict) and "error" not in security:
            if security.get("has_security_issues"):
                comment += f"### 🔒 Güvenlik Sorunları\n"
                for vuln in security.get("vulnerabilities", []):
                    comment += f"\n**⚠️ {vuln.get('file', 'unknown')}:{vuln.get('line', '?')}**\n"
                    comment += f"- **Risk:** {vuln.get('risk', 'unknown')}\n"
                    comment += f"- **Öneri:** {vuln.get('recommendation', 'N/A')}\n"
                comment += f"\n**Güvenlik Seviyesi:** {security.get('security_level', 'safe')}\n\n"
            else:
                comment += f"### 🔒 Güvenlik Kontrol\n"
                comment += f"**Durum:** {security.get('security_level', 'safe')}\n\n"

    # Performance Review
    if "performance" in analyses:
        perf = analyses["performance"]
        if isinstance(perf, dict) and "error" not in perf:
            suggestions = perf.get("suggestions", [])
            if suggestions:
                comment += f"### ⚡ Performance Önerileri\n"
                for sugg in suggestions:
                    comment += f"\n**📍 {sugg.get('file', 'unknown')}:{sugg.get('line', '?')}**\n"
                    comment += f"- **Sorun:** {sugg.get('issue', 'N/A')}\n"
                    comment += f"- **Öneri:** {sugg.get('recommendation', 'N/A')}\n"
                comment += f"\n**Optimizasyon Potansiyeli:** {perf.get('optimization_potential', 'low')}\n\n"

    # Add stats footer
    comment += "\n---\n"
    comment += f"**📊 Parser Stats:** {ParseStatistics.successful_parses} başarılı / {ParseStatistics.total_attempts} toplam ({ParseStatistics.get_success_rate():.0f}%)\n"
    comment += "*🤖 Bu yorum otomatik olarak oluşturulmuştur.*"

    return comment


@app.post("/webhook")
async def github_webhook(request: Request):
    """
    GitHub Webhook'dan gelen PR event'lerini handle et
    """

    try:
        # Ham body'yi al
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Signature doğrula
        if not verify_github_signature(body, signature):
            logger.error("❌ Geçersiz webhook signature!")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Payload'u parse et
        payload = await request.json()

        # Event tipini kontrol et
        event_type = request.headers.get("X-GitHub-Event", "")
        logger.info(f"🔔 Webhook alındı: event={event_type}")

        # Sadece pull_request event'leri işle
        if event_type != "pull_request":
            return {
                "status": "ignored",
                "reason": f"Event '{event_type}' desteklenmiyor",
            }

        action = payload.get("action")
        pr = payload.get("pull_request")

        if not pr:
            return {"status": "ignored", "reason": "PR data yok"}

        # Sadece "opened" ve "synchronize" event'leri işle
        if action not in ["opened", "synchronize"]:
            return {
                "status": "ignored",
                "reason": f"Action '{action}' review tetiklemez",
            }

        # Repository bilgilerini al
        repo_data = payload.get("repository", {})
        owner = repo_data.get("owner", {}).get("login")
        repo = repo_data.get("name")
        pr_number = pr.get("number")

        if not all([owner, repo, pr_number]):
            raise ValueError("PR metadata eksik")

        logger.info(f"🔔 Webhook: {owner}/{repo}#{pr_number} event={action}")

        # Review'u tetikle
        review_request = GitHubReviewRequest(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            review_types=["short_summary", "bug_detection", "security"],
        )

        return await github_review(review_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Webhook hatası: {str(e)}")
        return {"status": "error", "message": str(e)}
