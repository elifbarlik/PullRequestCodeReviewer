"""
SecPR-TR — GitHub App ana uygulama modülü.

Webhook event'leri:
  - pull_request (opened / synchronize)  → güvenlik analizi + PR yorumu + kullanım logu
  - installation (created / deleted)      → installations tablosuna kayıt / soft-delete
  - installation_repositories             → repo ekleme/çıkarma logu

Veri katmanı (Faz 2b) opsiyoneldir: DATABASE_URL yoksa tüm DB işlemleri
sessizce atlanır (bkz. app/db.py, app/repository.py).

Kimlik doğrulama:
  - Webhook imzası: HMAC SHA-256 (GITHUB_WEBHOOK_SECRET)  — secret zorunlu
  - API çağrıları: JWT → installation access token        — GitHub App flow
"""

from collections import OrderedDict
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from app.reviewer import (
    review_diff,
    truncate_diff,
    analyze_diff_stage1,
    ParseStatistics,
)
from app.github_client import GitHubAppClient
from app.semgrep_scanner import scan_diff, SemgrepNotAvailable, validate_configs
from app.diff_utils import parse_added_lines
from app.db import init_db
from app.repository import (
    upsert_installation,
    ensure_installation,
    deactivate_installation,
    update_installation_repos,
    record_usage,
    record_findings,
    get_stats_summary,
    get_installation_settings,
    set_installation_settings,
)
import json
import hmac
import hashlib
import os
import time
from dotenv import load_dotenv
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    """
    Uygulama açılışında DB tablolarını hazırla. DATABASE_URL yoksa
    init_db() sessizce False döner — uygulama DB'siz çalışmaya devam eder
    (bkz. app/db.py tasarım notu).
    """
    try:
        init_db()
    except Exception as e:
        # DB kurulumu patlasa bile servis ayağa kalkmalı — veri katmanı opsiyonel.
        logger.error(f"⚠️  init_db başarısız (DB'siz devam ediliyor): {e}")
    yield


app = FastAPI(title="SecPR-TR", version="0.3.0", lifespan=_lifespan)


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


class InstallationSettingsRequest(BaseModel):
    """
    PUT /installations/{id}/settings gövdesi. Alanların hepsi opsiyonel —
    yalnızca verilenler güncellenir.
    """
    enabled: Optional[bool] = None
    # None + reset_configs=False → dokunulmaz; liste → o ruleset'ler;
    # reset_configs=True → varsayılan ruleset'e dön (NULL'a çek)
    semgrep_configs: Optional[List[str]] = None
    reset_configs: bool = False


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
    """JSON parser istatistikleri + (DB açıksa) kurulum/analiz sayaçları."""
    stats = {
        "parser": {
            "total_attempts": ParseStatistics.total_attempts,
            "successful": ParseStatistics.successful_parses,
            "failed": ParseStatistics.failed_parses,
            "success_rate": f"{ParseStatistics.get_success_rate():.1f}%",
        }
    }
    db_summary = get_stats_summary()
    if db_summary is not None:
        stats["usage"] = db_summary
    return stats


# -------------------------------------------------------------------
# Endpoint: installation ayarları (Faz 2c)
# -------------------------------------------------------------------
# Henüz dashboard yok (Faz 5); ayarlar bu iki endpoint ile yönetilir.
# Erişim kontrolü: DB açık olmalı. Kimlik doğrulama Faz 4'te eklenecek —
# şimdilik iç/operasyonel kullanım varsayılıyor.

@app.get("/installations/{installation_id}/settings")
async def read_installation_settings(installation_id: int):
    """Bir installation'ın Semgrep ayarlarını döndürür (yoksa varsayılan)."""
    from app.db import db_enabled

    if not db_enabled():
        raise HTTPException(status_code=503, detail="Veri katmanı devre dışı (DATABASE_URL yok)")
    return {
        "installation_id": installation_id,
        **get_installation_settings(installation_id),
    }


@app.put("/installations/{installation_id}/settings")
async def update_installation_settings(
    installation_id: int, body: InstallationSettingsRequest
):
    """
    Installation ayarlarını günceller.

    - enabled=false  → bu installation için güvenlik taraması tamamen atlanır
    - semgrep_configs → yalnızca izinli ruleset'ler (ALLOWED_SEMGREP_CONFIGS);
      geçersizler sessizce elenir, hepsi geçersizse varsayılana dönülür
    - reset_configs=true → varsayılan ruleset'e dön
    """
    from app.db import db_enabled

    if not db_enabled():
        raise HTTPException(status_code=503, detail="Veri katmanı devre dışı (DATABASE_URL yok)")

    validated_configs = None
    if body.semgrep_configs is not None and not body.reset_configs:
        validated_configs = validate_configs(body.semgrep_configs)

    result = set_installation_settings(
        installation_id=installation_id,
        enabled=body.enabled,
        semgrep_configs=validated_configs,
        _clear_configs=body.reset_configs,
    )
    if result is None:
        raise HTTPException(status_code=500, detail="Ayar güncellenemedi")
    return {"installation_id": installation_id, **result}


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

# Büyük PR'larda Semgrep'e gönderilecek dosyaları sınırlamak için —
# bu uzantılar dışındakiler (lock dosyaları, üretilmiş kod, varlıklar)
# hem Semgrep ruleset kapsamı dışında hem de gereksiz I/O.
_SCANNABLE_EXTENSIONS = (
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php",
    ".c", ".cc", ".cpp", ".cs", ".scala", ".kt", ".rs", ".sh", ".yaml", ".yml",
)
_MAX_SCAN_FILES = 60


def _run_semgrep_for_pr(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    pr_number: int,
    diff_text: str,
    head_sha: str,
    pr_files: List[dict],
    configs: Optional[List[str]] = None,
) -> dict:
    """
    Verilen PR dosya listesinin içeriğini paralel çekip Semgrep'i çalıştırır.

    `head_sha` ve `pr_files` DIŞARIDAN verilir — bu fonksiyon artık kendi
    GitHub API çağrısını yapmaz (çağıran `get_pr_bundle` ile hepsini bir
    kez paralel çekiyor).

    Dönüş şekli main.py <-> reviewer.py arasındaki sözleşmedir:
      {"status": "ok", "findings": [...]}          — tarama başarıyla çalıştı
      {"status": "unavailable", "error": "..."}    — semgrep CLI kurulu değil
      {"status": "error", "error": "..."}          — GitHub API veya semgrep hata verdi

    "findings": [] (boş liste) ile status="unavailable"/"error" KESİNLİKLE
    karıştırılmamalı — biri "tarandı, temiz", diğeri "hiç taranamadı" demek.
    """
    if not head_sha:
        return {"status": "error", "error": "PR head SHA'sı bulunamadı"}

    # Silinen dosyaları ve taranamaz uzantıları ele; büyük PR'da tavan uygula.
    candidates = [
        f["filename"]
        for f in pr_files
        if f.get("status") != "removed"
        and f.get("filename")
        and f["filename"].endswith(_SCANNABLE_EXTENSIONS)
    ]
    skipped_for_cap = 0
    if len(candidates) > _MAX_SCAN_FILES:
        skipped_for_cap = len(candidates) - _MAX_SCAN_FILES
        candidates = candidates[:_MAX_SCAN_FILES]
        logger.warning(
            f"⚠️  {len(pr_files)} değişen dosya — Semgrep ilk {_MAX_SCAN_FILES} "
            f"taranabilir dosyayla sınırlandı ({skipped_for_cap} atlandı)"
        )

    try:
        files_content = client.get_files_content(owner, repo, candidates, ref=head_sha)
    except Exception as e:
        logger.error(f"❌ PR dosya içerikleri alınamadı, Semgrep atlanıyor: {e}")
        return {"status": "error", "error": f"PR dosyaları alınamadı: {e}"}

    try:
        findings = scan_diff(files_content, diff_text, configs=configs)
        result = {"status": "ok", "findings": findings}
        if skipped_for_cap:
            result["partial"] = f"{skipped_for_cap} dosya boyut sınırı nedeniyle taranmadı"
        return result
    except SemgrepNotAvailable as e:
        logger.warning(f"⚠️  Semgrep CLI kurulu değil, güvenlik taraması atlanıyor: {e}")
        return {"status": "unavailable", "error": str(e)}
    except Exception as e:
        logger.error(f"❌ Semgrep taraması başarısız: {e}")
        return {"status": "error", "error": str(e)}


async def _run_pr_review(
    installation_id: int,
    owner: str,
    repo: str,
    pr_number: int,
    review_types: Optional[List[str]] = None,
    account_login: Optional[str] = None,
    account_type: Optional[str] = None,
    action: str = "opened",
) -> dict:
    """
    Verilen PR'yi analiz eder ve sonuçları PR'e yorum olarak gönderir.

    Args:
        installation_id: Webhook'tan gelen installation.id
        owner, repo, pr_number: PR koordinatları
        review_types: Hangi analizler çalışsın
        account_login, account_type: Webhook payload'ındaki installation.account —
            installation.created event'i kaçırılmışsa DB kaydını lazy açmak için
        action: pull_request event action'ı ("opened" | "synchronize") —
            "synchronize"da mükerrer inline yorum kontrolü yapılır

    Returns:
        Sonuç özeti dict'i
    """
    if review_types is None:
        review_types = ["short_summary", "security"]

    started_at = time.monotonic()

    # installation.created event'i kaçırılmış olabilir (App bu DB devreye
    # girmeden önce kurulduysa GitHub o event'i bir daha göndermez) —
    # usage_logs INSERT'i FK violation ile patlamadan önce satırı garanti et.
    ensure_installation(
        installation_id,
        account_login=account_login or owner or "unknown",
        account_type=account_type or "unknown",
    )

    # Installation'a özgü client — kendi installation token'ını yönetir
    client = GitHubAppClient(installation_id=installation_id)

    # Faz 4.4: diff + details + files → TEK SEFERDE paralel çek (3 → ~1 round-trip)
    logger.info(f"📥 PR verisi alınıyor (paralel): {owner}/{repo}#{pr_number}")
    t_gh_start = time.monotonic()
    bundle = client.get_pr_bundle(owner=owner, repo=repo, pr_number=pr_number)
    diff_text = bundle["diff"]
    head_sha = bundle["details"].get("head", {}).get("sha")
    pr_files = bundle["files"]
    t_github_ms = int((time.monotonic() - t_gh_start) * 1000)

    if not diff_text or not diff_text.strip():
        raise ValueError("PR diff'i boş")

    original_size = len(diff_text)
    diff_to_analyze = truncate_diff(diff_text)
    was_truncated = len(diff_to_analyze) < original_size

    # Faz 2c: installation başına ayarlar — tarama açık mı, hangi ruleset'ler?
    settings = get_installation_settings(installation_id)
    review_types = list(review_types)
    if "security" in review_types and not settings["enabled"]:
        logger.info(f"⏭️  Güvenlik taraması bu installation için kapalı (id={installation_id})")
        review_types = [rt for rt in review_types if rt != "security"]

    # ── Faz 4.4: Semgrep taraması ile LLM analizini PARALEL çalıştır ──
    # short_summary Semgrep bulgusuna bağımlı değil (sadece diff'i özetler);
    # security açıklaması ise Semgrep sonucuna bağımlı, o yüzden review_diff'e
    # security_scan'i sonradan veriyoruz. İki uzun işi (Semgrep subprocess +
    # Gemini) aynı anda başlatmak toplam süreyi ~max(a,b)'ye indirir.
    run_security = "security" in review_types
    semgrep_configs = validate_configs(settings["semgrep_configs"]) if run_security else None
    t_scan_start = time.monotonic()

    def _semgrep_task():
        if not run_security:
            return None
        logger.info(f"🔬 Semgrep taraması başlıyor (config={semgrep_configs})...")
        r = _run_semgrep_for_pr(
            client, owner, repo, pr_number, diff_text,
            head_sha=head_sha, pr_files=pr_files, configs=semgrep_configs,
        )
        logger.info(f"🔬 Semgrep sonucu: status={r['status']}, "
                    f"bulgu={len(r.get('findings', []))}")
        return r

    def _llm_summary_task():
        # Sadece özet aşamasını çalıştır; detay/security review_diff'te.
        if "short_summary" not in review_types:
            return None
        logger.info("📊 LLM özet analizi (Semgrep'le paralel)...")
        return analyze_diff_stage1(diff_to_analyze)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_semgrep = ex.submit(_semgrep_task)
        f_summary = ex.submit(_llm_summary_task)
        security_scan = f_semgrep.result()
        stage1_result = f_summary.result()
    t_semgrep_ms = int((time.monotonic() - t_scan_start) * 1000)

    # LLM detay + security açıklaması (Semgrep sonucu artık hazır)
    logger.info(f"🔍 Analiz tamamlanıyor: {review_types}")
    t_gemini_start = time.monotonic()
    result = review_diff(
        diff_text=diff_to_analyze,
        review_types=review_types,
        security_scan=security_scan,
        precomputed_summary=stage1_result,
    )
    t_gemini_ms = int((time.monotonic() - t_gemini_start) * 1000)
    ParseStatistics.record_attempt(result["status"] == "success")

    # ── Yorum gönderme: satır-içi (inline) review + özet ─────────────
    if not head_sha:
        logger.warning("⚠️  PR head SHA yok — inline yorum atlanacak, özet yoruma düşülecek")

    added_lines = parse_added_lines(diff_text)
    inline_comments, unplaced = _build_inline_comments(result, added_lines)

    # synchronize'da mükerrer inline yorum atma — aynı (path,line) zaten
    # SecPR-TR tarafından yorumlanmışsa tekrar gönderme.
    if inline_comments and action == "synchronize":
        try:
            existing = client.list_review_comments(owner, repo, pr_number)
            already = {
                (c.get("path"), c.get("line"))
                for c in existing
                if _INLINE_MARKER in (c.get("body") or "")
            }
            before = len(inline_comments)
            inline_comments = [
                c for c in inline_comments if (c["path"], c["line"]) not in already
            ]
            if before != len(inline_comments):
                logger.info(f"↩️  {before - len(inline_comments)} mükerrer inline yorum atlandı")
        except Exception as e:
            logger.warning(f"⚠️  Mevcut yorumlar alınamadı, mükerrer kontrol atlandı: {e}")

    summary_body = _format_review_comment(
        result, was_truncated, inline_count=len(inline_comments), unplaced=unplaced
    )

    posted_inline = 0
    if inline_comments and head_sha:
        try:
            logger.info(f"💬 {len(inline_comments)} satır-içi yorumla review gönderiliyor...")
            client.create_review(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                body=summary_body,
                comments=inline_comments,
                commit_id=head_sha,
                event="COMMENT",
            )
            posted_inline = len(inline_comments)
        except Exception as e:
            # Inline review başarısız olursa (örn. satır yine de geçersiz) —
            # her şeyi özet yoruma koyup düz issue comment olarak gönder.
            logger.warning(f"⚠️  Inline review başarısız, özet yoruma düşülüyor: {e}")
            fallback_body = _format_review_comment(result, was_truncated)
            client.post_pr_comment(owner=owner, repo=repo, pr_number=pr_number, body=fallback_body)
    else:
        logger.info("💬 PR'e özet yorum gönderiliyor (inline yorum yok)...")
        client.post_pr_comment(owner=owner, repo=repo, pr_number=pr_number, body=summary_body)

    # ── Kullanım loglama (Faz 2b) ────────────────────────────────────
    # try/except repository.py'de zaten var, ama süre hesabı ve None
    # güvenliği için burada da savunmacı davranıyoruz — loglama hiçbir
    # koşulda PR yorumunu geçersiz kılmamalı.
    try:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        semgrep_status = security_scan.get("status") if security_scan else None
        finding_count = len(security_scan.get("findings", [])) if security_scan else 0
        # Faz 4.4: adım kırılımı — darboğazı veriyle görmek için.
        # DB kolonları Faz 4.3'te (Alembic) eklenecek; şimdilik log satırı.
        logger.info(
            f"⏱️  Süre kırılımı {owner}/{repo}#{pr_number}: "
            f"toplam={duration_ms}ms | github={t_github_ms}ms | "
            f"semgrep∥özet={t_semgrep_ms}ms | gemini_detay={t_gemini_ms}ms"
        )
        usage_log_id = record_usage(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            review_types=review_types,
            diff_size=original_size,
            was_truncated=was_truncated,
            semgrep_status=semgrep_status,
            finding_count=finding_count,
            parse_success=(result["status"] == "success"),
            duration_ms=duration_ms,
        )
        if security_scan and security_scan.get("status") == "ok":
            record_findings(
                usage_log_id=usage_log_id,
                installation_id=installation_id,
                findings=security_scan.get("findings", []),
            )
    except Exception as e:
        logger.error(f"⚠️  Kullanım loglama başarısız (yutuldu): {e}")

    return {
        "status": "success",
        "message": f"PR #{pr_number} incelendi",
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "diff_size": original_size,
        "was_truncated": was_truncated,
        "analyses": result["analyses"],
        "timing_ms": {
            "total": duration_ms,
            "github": t_github_ms,
            "semgrep_and_summary": t_semgrep_ms,
            "gemini_detail": t_gemini_ms,
        },
    }


# -------------------------------------------------------------------
# Webhook ana endpoint
# -------------------------------------------------------------------

# Faz 4.4: son işlenen X-GitHub-Delivery id'leri — GitHub bir webhook'a
# 10 sn içinde 2xx alamazsa AYNI delivery'yi retry eder. Analiz arka planda
# çalıştığı için artık 10 sn sorun değil, ama retry yine de gelebilir
# (ağ gecikmesi). Bu LRU, aynı delivery'nin ikinci kez analiz edilip
# mükerrer yorum atmasını önler. Process-local; tek instance için yeterli,
# çok instance'a çıkılırsa Redis/DB'ye taşınır.
_SEEN_DELIVERIES: "OrderedDict[str, float]" = OrderedDict()
_SEEN_DELIVERIES_MAX = 500


def _already_processed(delivery_id: str) -> bool:
    """delivery_id daha önce görüldüyse True; görülmediyse kaydeder ve False döner."""
    if not delivery_id:
        return False
    if delivery_id in _SEEN_DELIVERIES:
        return True
    _SEEN_DELIVERIES[delivery_id] = time.monotonic()
    if len(_SEEN_DELIVERIES) > _SEEN_DELIVERIES_MAX:
        _SEEN_DELIVERIES.popitem(last=False)
    return False


async def _process_pr_event_bg(action: str, payload: dict) -> None:
    """pull_request analizini arka planda çalıştırır — hataları yutar."""
    try:
        await _handle_pull_request_event(action, payload)
    except Exception as e:
        logger.error(f"❌ Arka plan PR analizi başarısız: {e}")


@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    GitHub App webhook endpoint'i.

    Faz 4.4: pull_request analizi UZUN sürebilir (Semgrep + 2× Gemini).
    GitHub webhook'a 10 sn içinde yanıt bekler; aksi halde "failed delivery"
    işaretleyip retry eder → mükerrer analiz + mükerrer yorum. Bu yüzden:
      1. İmzayı doğrula
      2. X-GitHub-Delivery ile mükerrer mü kontrol et
      3. Analizi BackgroundTasks'e ver, hemen 202 dön

    installation / installation_repositories event'leri hızlı (sadece DB
    yazımı) — onlar senkron kalır.
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
        delivery_id = request.headers.get("X-GitHub-Delivery", "")

        logger.info(f"🔔 Webhook: event={event_type} action={action} delivery={delivery_id}")

        if _already_processed(delivery_id):
            logger.info(f"↩️  Mükerrer delivery, atlanıyor: {delivery_id}")
            return {"status": "duplicate", "delivery": delivery_id}

        # ── installation event'leri (hızlı, senkron) ─────────────────
        if event_type == "installation":
            return await _handle_installation_event(action, payload)

        if event_type == "installation_repositories":
            return await _handle_installation_repositories_event(action, payload)

        # ── pull_request (uzun, arka planda) ─────────────────────────
        if event_type == "pull_request":
            if action not in ("opened", "synchronize"):
                return {"status": "ignored", "reason": f"pull_request.{action} analiz tetiklemez"}
            background_tasks.add_task(_process_pr_event_bg, action, payload)
            return {"status": "accepted", "event": "pull_request", "action": action}

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

    repository_selection = payload.get("installation", {}).get("repository_selection")

    if action == "created":
        logger.info(
            f"🎉 Yeni kurulum: installation_id={installation_id} "
            f"hesap={account_login} ({account_type})"
        )
        upsert_installation(
            installation_id=installation_id,
            account_login=account_login,
            account_type=account_type,
            repository_selection=repository_selection,
        )
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
        deactivate_installation(installation_id)
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

    update_installation_repos(installation_id, repos_added, repos_removed)
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

    # installation.account payload'da her zaman gelmez (pull_request event'inde
    # genelde sadece installation.id var); repo.owner'a düş.
    repo_owner = repo_data.get("owner", {})
    account_login = installation.get("account", {}).get("login") or repo_owner.get("login")
    account_type = installation.get("account", {}).get("type") or repo_owner.get("type")

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
        account_login=account_login,
        account_type=account_type,
        action=action,
    )


# -------------------------------------------------------------------
# Yorum formatlama + satır-içi (inline) yorum üretimi
# -------------------------------------------------------------------

# Inline yorum gövdelerine gömülen gizli işaret — synchronize'da
# SecPR-TR'nin kendi eski yorumlarını tanıyıp mükerrer atmamak için.
_INLINE_MARKER = "<!-- secpr-tr:finding -->"


def _build_inline_comments(result: dict, added_lines: dict):
    """
    Güvenlik bulgularını GitHub review API'sinin beklediği inline yorum
    listesine çevirir.

    Bir bulgu ancak dosyası + satırı PR diff'inde (eklenen/değişen satırlar
    arasında) gerçekten varsa inline yorumlanabilir — GitHub aksi halde
    tüm review'ı 422 ile reddeder. Yerleştirilemeyen bulgular `unplaced`
    listesine konur ve özet yoruma düşer.

    Returns:
        (inline_comments, unplaced)
        inline_comments: [{path, line, body}, ...]
        unplaced: [vuln, ...] — diff'te satırı bulunamayan bulgular
    """
    analyses = result.get("analyses", {})
    security = analyses.get("security")
    if not isinstance(security, dict) or "error" in security:
        return [], []
    if not security.get("has_security_issues"):
        return [], []

    inline_comments = []
    unplaced = []
    for vuln in security.get("vulnerabilities", []):
        path = vuln.get("file")
        line = vuln.get("line")
        try:
            line = int(line)
        except (TypeError, ValueError):
            line = None

        if path and line and line in added_lines.get(path, set()):
            body = (
                f"{_INLINE_MARKER}\n"
                f"### 🔒 {vuln.get('type', 'Güvenlik bulgusu')}\n"
                f"**Risk:** {vuln.get('risk', 'bilinmiyor')}\n\n"
                f"**Neden riskli?** {vuln.get('description', 'N/A')}\n\n"
                f"**Nasıl düzeltilir?** {vuln.get('recommendation', 'N/A')}\n\n"
                f"<sub>Semgrep + Gemini · SecPR-TR</sub>"
            )
            inline_comments.append({"path": path, "line": line, "body": body})
        else:
            unplaced.append(vuln)

    return inline_comments, unplaced


def _format_review_comment(
    result: dict,
    was_truncated: bool = False,
    inline_count: int = 0,
    unplaced: Optional[list] = None,
) -> str:
    """
    Review sonuçlarını GitHub PR (özet) yorumu olarak formatlar.

    inline_count > 0 ise güvenlik bulguları satır satır işaretlenmiştir;
    özet bloğu kısalır ve sadece diff'e yerleştirilemeyen (`unplaced`)
    bulguları tam metniyle listeler.
    """
    unplaced = unplaced or []

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
            if security.get("scan_error"):
                # Tarama hiç çalışmadı — ASLA "güvenli" denmez, şeffaf uyarı verilir
                comment += "### ⚠️ Güvenlik Taraması Yapılamadı\n"
                comment += f"Bu PR için otomatik güvenlik taraması tamamlanamadı: {security['scan_error']}\n"
                comment += "Lütfen değişiklikleri manuel olarak gözden geçirin.\n\n"
            elif security.get("has_security_issues"):
                total = len(security.get("vulnerabilities", []))
                comment += "### 🚨 Güvenlik Bulguları (Semgrep + Gemini)\n"
                if inline_count:
                    comment += (
                        f"**{inline_count}/{total}** bulgu ilgili satırlara yorum olarak "
                        f"eklendi (aşağıda ↑ değişiklikler sekmesinde görünür).\n\n"
                    )
                # Inline yerleştirilemeyen (veya inline hiç kullanılmadıysa hepsi) bulgular:
                to_list = unplaced if inline_count else security.get("vulnerabilities", [])
                if to_list:
                    if inline_count:
                        comment += "Satıra yerleştirilemeyen bulgular:\n"
                    for vuln in to_list:
                        comment += f"\n**⚠️ {vuln.get('file', 'bilinmiyor')}:{vuln.get('line', '?')}** — {vuln.get('type', 'bilinmiyor')}\n"
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
