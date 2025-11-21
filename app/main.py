from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from app.reviewer import review_diff, truncate_diff
from app.github_client import GitHubClient
import json
import hmac
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="PR Code Reviewer", version="0.1.0")

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

    # GitHub webhook secret'ı al
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        print("⚠️  GITHUB_WEBHOOK_SECRET tanımlanmamış, signature kontrolü atlanıyor")
        return True  # Development ortamında secret yoksa geçebilir

    # Signature formatı: sha256=<hash>
    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header.split("=")[1]

    # HMAC hesapla
    mac = hmac.new(
        webhook_secret.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
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
    analyses: dict

class GitHubReviewRequest(BaseModel):
    """GitHub PR otomatik review isteği"""
    owner: str
    repo: str
    pr_number: int
    review_types: Optional[List[str]] = ["short_summary", "bug_detection"]

@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/local-review", response_model=ReviewResponse)
async def local_review(request: DiffRequest):
    """Local diff'i analiz et (manuel)"""
    if not request.diff_text or len(request.diff_text.strip()) == 0:
        raise HTTPException(status_code=400, detail="diff_text boş olamaz")

    diff_to_analyze = truncate_diff(request.diff_text, max_length=3000)

    valid_types = ["short_summary", "bug_detection", "performance", "security"]
    review_types = request.review_types or ["short_summary", "bug_detection"]

    for rt in review_types:
        if rt not in valid_types:
            raise HTTPException(status_code=400, detail=f"Geçersiz review_type: {rt}")

    try:
        result = review_diff(diff_text=diff_to_analyze, review_types=review_types)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM hatası: {str(e)}")

    return ReviewResponse(
        status=result["status"],
        file_name=request.file_name,
        diff_length=len(request.diff_text),
        analyses=result["analyses"]
    )


@app.post("/github-review")
async def github_review(request: GitHubReviewRequest):
    """
    GitHub PR'den diff al, analiz et, sonuçları PR'ye comment olarak gönder

    Örnek kullanım:
    POST /github-review
    {
        "owner": "elifbarlik",
        "repo": "PR-Reviewer-Test-Repo",
        "pr_number": 2,
        "review_types": ["short_summary", "bug_detection", "security"]
    }
    """

    try:
        # GitHub Client'ı initialize et
        github_client = GitHubClient()

        # PR'den diff'i al
        print(f"📥 PR'den diff alınıyor: {request.owner}/{request.repo}#{request.pr_number}")
        diff_text = github_client.get_pr_diff(
            owner=request.owner,
            repo=request.repo,
            pr_number=request.pr_number
        )

        if not diff_text or len(diff_text.strip()) == 0:
            raise HTTPException(status_code=400, detail="PR diff'i boş")

        # Diff'i kırp (çok uzunsa)
        diff_to_analyze = truncate_diff(diff_text, max_length=3000)

        # Review yap
        print(f"🔍 Analiz yapılıyor: {request.review_types}")
        result = review_diff(
            diff_text=diff_to_analyze,
            review_types=request.review_types or ["short_summary", "bug_detection"]
        )

        # Sonuçları PR'e comment olarak gönder
        comment_body = _format_review_comment(result)

        print(f"💬 Comment gönderiliyor PR'ye...")
        github_client.post_pr_comment(
            owner=request.owner,
            repo=request.repo,
            pr_number=request.pr_number,
            body=comment_body
        )

        return {
            "status": "success",
            "message": f"PR #{request.pr_number} review tamamlandı",
            "owner": request.owner,
            "repo": request.repo,
            "pr_number": request.pr_number,
            "analyses": result["analyses"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub review hatası: {str(e)}")


def _format_review_comment(result: dict) -> str:
    """Review sonuçlarını GitHub comment formatına çevir"""

    comment = "## 🤖 PR Code Reviewer - Otomatik Analiz\n\n"

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

    # Footer
    comment += "\n---\n"
    comment += "*🤖 Bu yorum otomatik olarak oluşturulmuştur. [PR Code Reviewer](https://github.com) tarafından.*"

    return comment


@app.post("/webhook")
async def github_webhook(request: Request):
    """
    GitHub Webhook'dan gelen PR event'lerini handle et (HMAC signature doğrulamalı)

    Workflow:
    1. PR açıldı/updated oldu
    2. Webhook POST yapıyor bu endpoint'e
    3. Signature doğrulanır (HMAC SHA-256)
    4. Otomatik review başlatılır

    GitHub Settings > Webhooks'a ekle:
    - URL: https://YOUR_NGROK_URL/webhook
    - Content type: application/json
    - Secret: GITHUB_WEBHOOK_SECRET ile aynı değer
    - Events: Pull requests
    """

    try:
        # Ham body'yi al (signature kontrolü için gerekli)
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Signature doğrula
        if not verify_github_signature(body, signature):
            print("❌ Geçersiz webhook signature!")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Payload'u parse et
        payload = await request.json()

        # Event tipini kontrol et
        event_type = request.headers.get("X-GitHub-Event", "")
        print(f"🔔 Webhook alındı: event={event_type}")

        # Sadece pull_request event'leri işle
        if event_type != "pull_request":
            return {"status": "ignored", "reason": f"Event '{event_type}' desteklenmiyor"}

        action = payload.get("action")
        pr = payload.get("pull_request")

        if not pr:
            return {"status": "ignored", "reason": "PR data yok"}

        # Sadece "opened" ve "synchronize" event'leri işle
        if action not in ["opened", "synchronize"]:
            return {"status": "ignored", "reason": f"Action '{action}' review tetiklemez"}

        # Repository bilgilerini al
        repo_data = payload.get("repository", {})
        owner = repo_data.get("owner", {}).get("login")
        repo = repo_data.get("name")
        pr_number = pr.get("number")

        if not all([owner, repo, pr_number]):
            raise ValueError("PR metadata eksik")

        print(f"🔔 Webhook: {owner}/{repo}#{pr_number} event={action}")

        # Review'u tetikle
        review_request = GitHubReviewRequest(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            review_types=["short_summary", "bug_detection", "security"]
        )

        return await github_review(review_request)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Webhook hatası: {str(e)}")
        return {"status": "error", "message": str(e)}