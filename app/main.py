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
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from typing import List, Optional
from app.reviewer import (
    review_diff,
    truncate_diff,
    analyze_diff_stage1,
    ParseStatistics,
)
from app.github_client import GitHubAppClient
from app.semgrep_scanner import (
    scan_diff,
    SemgrepNotAvailable,
    validate_configs,
    build_scan_plan,
    MAX_DIFF_BYTES,
    MAX_SCAN_FILE_BYTES,
)
from app.diff_utils import parse_added_lines
from app.db import init_db
from app.web import router as web_router
from app.cost_control import LLMUsageCollector, llm_response_cache
from app.github_security import (
    validate_delivery_id,
    validate_installation_id,
    validate_webhook_event,
)
from app.repository import (
from app.github_oauth import start_login, finish_login, require_user, current_user, logout
    upsert_installation,
    ensure_installation,
    deactivate_installation,
    update_installation_repos,
    record_usage,
    record_findings,
    get_stats_summary,
    get_dashboard_summary,
    get_recent_review_runs,
    get_review_run_detail,
    get_installation_settings,
    set_installation_settings,
    get_detailed_metrics,
    check_rate_limit,
    upsert_repository,
    create_review_run,
    update_review_run,
    claim_webhook_delivery,
    mark_webhook_delivery,
    recover_stale_review_runs,
)
import json
import hmac
import hashlib
import os
import secrets as _secrets
import time
from dotenv import load_dotenv
import logging
import shutil

from sqlalchemy import text

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
except ImportError:  # pragma: no cover - dependency is installed in production
    sentry_sdk = None
    FastApiIntegration = None
    SqlalchemyIntegration = None

try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:
    try:
        from pythonjsonlogger.jsonlogger import JsonFormatter
    except ImportError:  # optional locally; production image installs it
        JsonFormatter = None

load_dotenv()

def _configure_logging() -> None:
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()
    if log_format == "json" and JsonFormatter is not None:
        handler = logging.StreamHandler()
        handler.setFormatter(
            JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    elif log_format == "json":
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            "LOG_FORMAT=json requested but python-json-logger is not installed; using text logs"
        )
    else:
        logging.basicConfig(level=logging.INFO)


_configure_logging()
logger = logging.getLogger(__name__)

APP_VERSION = "0.5.0"
HOURLY_PR_LIMIT = max(1, int(os.getenv("HOURLY_PR_LIMIT", "50")))

_SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
_SENTRY_ENABLED = bool(_SENTRY_DSN and sentry_sdk is not None)
if _SENTRY_DSN and sentry_sdk is not None:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.getenv("FLY_APP_NAME", os.getenv("ENVIRONMENT", "local")),
        release=f"secpr-tr@{APP_VERSION}",
        send_default_pii=False,
    )
# Startup migration state is intentionally kept separate from the live
# database connectivity check exposed by /health.
_startup_db_status = "not_started"

@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    """
    Uygulama açılışında Alembic migration'larını uygula.

    DATABASE_URL yoksa DB intentionally disabled kalır. DATABASE_URL
    tanımlı olup migration başarısız olursa servis yine import edilebilir;
    /health bu durumu açıkça raporlar.
    """
    global _startup_db_status
    try:
        migrated = init_db()
        _startup_db_status = "ok" if migrated else "disabled"
        if migrated:
            recovered = recover_stale_review_runs()
            if recovered:
                logger.warning(f"♻️ {recovered} stale review run recovered as failed")
    except Exception as e:
        _startup_db_status = "error"
        logger.error(f"⚠️  Alembic startup migration başarısız: {e}")
    yield


app = FastAPI(title="SecPR-TR", version=APP_VERSION, lifespan=_lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(web_router)

# Rate limiting: local review endpoint
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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

def _database_health_status() -> str:
    """Return a safe database health state without exposing connection details."""
    from app.db import db_enabled, get_engine

    if not db_enabled():
        return "disabled"
    if _startup_db_status == "error":
        return "error"

    try:
        engine = get_engine()
        if engine is None:
            return "error"
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("❌ /health database connectivity check failed")
        return "error"


def _configured(value: str) -> str:
    return "configured" if bool(os.getenv(value, "").strip()) else "missing"


@app.get("/health")
async def health_check():
    """Production health/status endpoint without revealing secret values."""
    database_status = _database_health_status()
    semgrep_status = "ok" if shutil.which("semgrep") else "unavailable"
    checks = {
        "database": database_status,
        "semgrep": semgrep_status,
        "github": (
            "configured"
            if os.getenv("GITHUB_APP_ID", "").strip()
            and (os.getenv("GITHUB_APP_PRIVATE_KEY", "").strip()
                 or os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "").strip())
            else "missing"
        ),
        "gemini": _configured("GEMINI_API_KEY"),
        "webhook": _configured("GITHUB_WEBHOOK_SECRET"),
        "sentry": "configured" if _SENTRY_ENABLED else "not_configured",
    }
    ready = (
        database_status in {"ok", "disabled"}
        and semgrep_status == "ok"
        and checks["github"] == "configured"
        and checks["gemini"] == "configured"
        and checks["webhook"] == "configured"
    )
    return {
        "status": "ok" if ready else "degraded",
        "version": APP_VERSION,
        "app": "SecPR-TR",
        "checks": checks,
    }


# -------------------------------------------------------------------
# Product dashboard API (Faz 10)
# -------------------------------------------------------------------

@app.get("/dashboard/api/summary")
async def dashboard_summary(request: Request):
    user = require_user(request)
    result = get_dashboard_summary(user.get("installations", []))
    if result is None:
        raise HTTPException(status_code=503, detail="Dashboard veri katmanı kullanılamıyor")
    return result


@app.get("/dashboard/api/reviews")
async def dashboard_reviews(request: Request, limit: int = 20):
    user = require_user(request)
    result = get_recent_review_runs(limit, user.get("installations", []))
    if result is None:
        raise HTTPException(status_code=503, detail="Dashboard veri katmanı kullanılamıyor")
    return {"reviews": result}


@app.get("/dashboard/api/reviews/{review_run_id}")
async def dashboard_review_detail(review_run_id: int, request: Request):
    user = require_user(request)
    result = get_review_run_detail(review_run_id, user.get("installations", []))
    if result is None:
        raise HTTPException(status_code=404, detail="Review bulunamadı")
    return result


# -------------------------------------------------------------------
# GitHub user authentication (Faz 11)
# -------------------------------------------------------------------

@app.get("/auth/github", include_in_schema=False)
async def github_login(request: Request):
    try:
        return start_login(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/auth/github/callback", include_in_schema=False)
async def github_callback(request: Request, code: str = "", state: str = ""):
    if not code or not state:
        raise HTTPException(status_code=400, detail="OAuth callback parametreleri eksik")
    try:
        return finish_login(request, code, state)
    except HTTPException:
        raise
    except requests.RequestException:
        logger.exception("GitHub OAuth callback failed")
        raise HTTPException(status_code=502, detail="GitHub OAuth işlemi başarısız")


@app.post("/auth/logout", include_in_schema=False)
async def github_logout():
    return logout()


@app.get("/auth/me", include_in_schema=False)
async def github_me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="GitHub ile giriş gerekli")
    return {"id": user["sub"], "login": user["login"], "installations": len(user.get("installations", []))}


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
# Admin endpoint authentication
# -------------------------------------------------------------------

def _verify_admin_token(request: Request) -> None:
    """
    Admin endpoint'leri için token doğrulama.

    ADMIN_SECRET tanımlı değilse endpoint erişimi tamamen engellenir.
    Token karşılaştırması timing attack'lere karşı sabit zamanlıdır.
    """
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if not admin_secret:
        raise HTTPException(
            status_code=503,
            detail="Admin token yapılandırılmamış — ADMIN_SECRET eksik",
        )

    token = request.headers.get("X-Admin-Token", "")
    if not _secrets.compare_digest(admin_secret, token):
        raise HTTPException(status_code=401, detail="Geçersiz admin token")


@app.post("/admin/logging-test")
async def admin_logging_test(request: Request):
    """Emit one authenticated structured-log smoke-test record."""
    _verify_admin_token(request)
    logger.warning(
        "SecPR-TR structured logging smoke test",
        extra={
            "secpr_smoke_test": True,
            "app_version": APP_VERSION,
        },
    )
    return {
        "status": "logged",
        "event": "structured-log-smoke-test",
        "release": f"secpr-tr@{APP_VERSION}",
    }


@app.post("/admin/sentry-test")
async def admin_sentry_test(request: Request):
    """Send one explicit, authenticated Sentry smoke-test event."""
    _verify_admin_token(request)

    if sentry_sdk is None:
        raise HTTPException(status_code=503, detail="sentry-sdk kurulu değil")
    if not _SENTRY_DSN:
        raise HTTPException(status_code=503, detail="SENTRY_DSN yapılandırılmamış")

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("secpr_smoke_test", "true")
        scope.set_tag("app_version", APP_VERSION)
        event_id = sentry_sdk.capture_message(
            "SecPR-TR Sentry production smoke test",
            level="warning",
        )
    sentry_sdk.flush(timeout=2.0)

    return {
        "status": "sent",
        "event_id": event_id,
        "release": f"secpr-tr@{APP_VERSION}",
    }


# -------------------------------------------------------------------
# Endpoint: installation ayarları (Faz 2c)
# -------------------------------------------------------------------
# Henüz dashboard yok (Faz 5); ayarlar bu iki endpoint ile yönetilir.
# Erişim kontrolü: DB açık olmalı. Kimlik doğrulama Faz 4'te eklenecek —
# şimdilik iç/operasyonel kullanım varsayılıyor.

@app.get("/installations/{installation_id}/settings")
async def read_installation_settings(installation_id: int, request: Request):
    """Bir installation'ın Semgrep ayarlarını döndürür (yoksa varsayılan)."""
    from app.db import db_enabled

    _verify_admin_token(request)

    if not db_enabled():
        raise HTTPException(status_code=503, detail="Veri katmanı devre dışı (DATABASE_URL yok)")
    return {
        "installation_id": installation_id,
        **get_installation_settings(installation_id),
    }


@app.put("/installations/{installation_id}/settings")
async def update_installation_settings(
    installation_id: int, body: InstallationSettingsRequest, request: Request
):
    """
    Installation ayarlarını günceller.

    - enabled=false  → bu installation için güvenlik taraması tamamen atlanır
    - semgrep_configs → yalnızca izinli ruleset'ler (ALLOWED_SEMGREP_CONFIGS);
      geçersizler sessizce elenir, hepsi geçersizse varsayılana dönülür
    - reset_configs=true → varsayılan ruleset'e dön
    """
    from app.db import db_enabled

    _verify_admin_token(request)

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
@limiter.limit("10/hour")
async def local_review(request: Request, body: DiffRequest):
    """Doğrudan gönderilen diff'i analiz eder (webhook gerektirmez)."""

    if not body.diff_text or len(body.diff_text.strip()) == 0:
        raise HTTPException(status_code=400, detail="diff_text boş olamaz")

    original_size = len(body.diff_text)
    diff_to_analyze = truncate_diff(body.diff_text, max_length=3000)
    was_truncated = len(diff_to_analyze) < original_size

    valid_types = ["short_summary", "bug_detection", "performance", "security"]
    review_types = body.review_types or ["short_summary", "bug_detection"]

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
        file_name=body.file_name,
        diff_length=original_size,
        was_truncated=was_truncated,
        analyses=result["analyses"],
        metadata=result.get("metadata"),
    )


# -------------------------------------------------------------------
# İç yardımcı: PR analizi ve yorum gönderme
# -------------------------------------------------------------------

# Faz 6: Semgrep tarama politikası semgrep_scanner.py'deki tek sözleşmeden
# gelir; burada ayrı bir uzantı listesi tutulmaz.
_MAX_SCAN_FILES = 60  # backward-compatible local alias; Phase 6 contract lives in semgrep_scanner


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
    """Run the Phase 6 bounded Semgrep scan and expose partial-scan state."""
    if not head_sha:
        return {"status": "error", "error": "PR head SHA'sı bulunamadı"}

    diff_bytes = len(diff_text.encode("utf-8", errors="replace"))
    if diff_bytes > MAX_DIFF_BYTES:
        return {
            "status": "unavailable",
            "error": (
                f"Diff boyutu {diff_bytes} byte; güvenlik taraması için "
                f"izin verilen üst sınır {MAX_DIFF_BYTES} byte."
            ),
            "partial": True,
            "partial_reason": "diff_size_limit",
            "diff_bytes": diff_bytes,
            "max_diff_bytes": MAX_DIFF_BYTES,
        }

    plan = build_scan_plan(pr_files, max_files=_MAX_SCAN_FILES)
    candidates = plan["candidates"]
    skipped_for_cap = plan["skipped_for_cap"]
    unsupported_count = plan["unsupported_count"]

    if not candidates:
        # PR yalnızca desteklenmeyen/çıkarılmış dosyalardan oluşuyorsa bu bir
        # scanner arızası değildir; kapsam eksiktir ve sonuç "safe" olamaz.
        return {
            "status": "ok",
            "findings": [],
            "partial": True,
            "partial_reason": "unsupported_files" if unsupported_count else "no_scan_targets",
            "unsupported_count": unsupported_count,
            "removed_count": plan["removed_count"],
            "message": (
                "Semgrep kapsamına girebilen değişmiş dosya bulunamadı; "
                "güvenlik taraması tam kapsamlı değildir."
            ),
        }

    try:
        files_content = client.get_files_content(owner, repo, candidates, ref=head_sha)
    except Exception as e:
        logger.error(f"❌ PR dosya içerikleri alınamadı, Semgrep atlanıyor: {e}")
        return {"status": "error", "error": f"PR dosyaları alınamadı: {e}"}

    oversized = [
        path for path, content in files_content.items()
        if len(content.encode("utf-8", errors="replace")) > MAX_SCAN_FILE_BYTES
    ]
    for path in oversized:
        files_content.pop(path, None)

    try:
        findings = scan_diff(files_content, diff_text, configs=configs)
        result = {"status": "ok", "findings": findings}

        skipped = skipped_for_cap + unsupported_count + len(oversized)
        if skipped:
            reasons = []
            if skipped_for_cap:
                reasons.append("file_scope_limit")
            if unsupported_count:
                reasons.append("unsupported_files")
            if oversized:
                reasons.append("file_size_limit")
            result.update({
                "partial": True,
                "partial_reason": ",".join(reasons),
                "supported_count": plan["supported_count"],
                "scanned_count": len(files_content),
                "unsupported_count": unsupported_count,
                "skipped_for_cap": skipped_for_cap,
                "oversized_count": len(oversized),
                "removed_count": plan["removed_count"],
                "message": (
                    f"Partial scan: {skipped} değişen dosya güvenlik taramasının "
                    "kapsamı dışında kaldı."
                ),
            })
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
    llm_usage = LLMUsageCollector()

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

    if not check_rate_limit(installation_id, HOURLY_PR_LIMIT):
        logger.warning(
            f"⚠️ Saatlik PR analiz limiti aşıldı: installation={installation_id} "
            f"limit={HOURLY_PR_LIMIT}"
        )
        client.post_pr_comment(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            body=(
                "⏳ **SecPR-TR:** Bu installation için saatlik otomatik PR "
                f"analiz limiti ({HOURLY_PR_LIMIT}) doldu. Bir sonraki saat "
                "içinde yeni analiz başlatılmayacaktır."
            ),
        )
        return {
            "status": "rate_limited",
            "message": "Saatlik PR analiz limitine ulaşıldı",
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "limit_per_hour": HOURLY_PR_LIMIT,
        }

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
        return analyze_diff_stage1(diff_to_analyze, usage=llm_usage)

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
        usage=llm_usage,
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
            t_github_ms=t_github_ms,
            t_semgrep_ms=t_semgrep_ms,
            t_gemini_ms=t_gemini_ms,
            input_tokens=llm_usage.snapshot()["input_tokens"],
            output_tokens=llm_usage.snapshot()["output_tokens"],
            gemini_cost_usd=llm_usage.snapshot()["cost_usd"],
            llm_calls=llm_usage.snapshot()["calls"],
            llm_cache_hits=llm_usage.snapshot()["cache_hits"],
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
# Endpoint: operasyonel / maliyet metrikleri
# -------------------------------------------------------------------

@app.get("/metrics")
async def metrics():
    usage = get_detailed_metrics()
    return {
        "parser_success_rate_pct": round(ParseStatistics.get_success_rate(), 1),
        "llm_cache": llm_response_cache.stats() if "llm_response_cache" in globals() else None,
        "usage": usage,
    }


# -------------------------------------------------------------------
# Webhook ana endpoint
# -------------------------------------------------------------------

# Durable DB-backed idempotency is the source of truth when DB is available.
# Process-local LRU remains only as a fallback when DB is disabled/unreachable.
_SEEN_DELIVERIES: "OrderedDict[str, float]" = OrderedDict()
_SEEN_DELIVERIES_MAX = 500


def _already_processed(
    delivery_id: str,
    event_type: str = "",
    action: str = "",
    installation_id: Optional[int] = None,
    repository_id: Optional[int] = None,
) -> bool:
    if not delivery_id:
        return False
    durable = claim_webhook_delivery(
        delivery_id, event_type, action, installation_id, repository_id
    )
    if durable is not None:
        return durable
    if delivery_id in _SEEN_DELIVERIES:
        return True
    _SEEN_DELIVERIES[delivery_id] = time.monotonic()
    if len(_SEEN_DELIVERIES) > _SEEN_DELIVERIES_MAX:
        _SEEN_DELIVERIES.popitem(last=False)
    return False


async def _process_pr_event_bg(
    action: str, payload: dict, delivery_id: str, review_run_id: Optional[int]
) -> None:
    """Run the PR review asynchronously and persist its lifecycle."""
    update_review_run(review_run_id, "running")
    try:
        result = await _handle_pull_request_event(action, payload)
        security = result.get("analyses", {}).get("security", {}) if isinstance(result, dict) else {}
        files_scanned = int(payload.get("pull_request", {}).get("changed_files") or 0)
        findings_count = len(security.get("vulnerabilities", [])) if isinstance(security, dict) else 0
        update_review_run(
            review_run_id,
            "completed",
            files_scanned=files_scanned,
            findings_count=findings_count,
        )
        mark_webhook_delivery(delivery_id, "processed")
    except Exception as e:
        logger.error(f"❌ Arka plan PR analizi başarısız: {e}")
        update_review_run(review_run_id, "failed", error=str(e))
        mark_webhook_delivery(delivery_id, "failed", error=str(e))
        if sentry_sdk is not None:
            sentry_sdk.capture_exception(e)


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
        raw_event_type = request.headers.get("X-GitHub-Event", "")
        try:
            event_type = validate_webhook_event(raw_event_type)
            delivery_id = validate_delivery_id(
                request.headers.get("X-GitHub-Delivery", "")
            )
            installation_id = validate_installation_id(
                payload.get("installation", {}).get("id"),
                required=raw_event_type != "ping",
            )
        except ValueError as exc:
            logger.warning("Rejected invalid GitHub webhook metadata: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid webhook metadata")

        action = payload.get("action", "")
        logger.info(
            "🔔 Webhook: event=%s action=%s delivery=%s",
            event_type,
            action,
            delivery_id,
        )

        repository_data = payload.get("repository", {})
        repository_id = repository_data.get("id")

        # Installation/repository-management events can arrive before their
        # entities exist locally. Claim them without FK metadata.
        if event_type == "installation":
            if _already_processed(delivery_id, event_type, action, None, None):
                return {"status": "duplicate", "delivery": delivery_id}
            try:
                result = await _handle_installation_event(action, payload)
                mark_webhook_delivery(delivery_id, "processed")
                return result
            except Exception as e:
                mark_webhook_delivery(delivery_id, "failed", str(e))
                raise

        if event_type == "installation_repositories":
            if _already_processed(delivery_id, event_type, action, None, None):
                return {"status": "duplicate", "delivery": delivery_id}
            try:
                result = await _handle_installation_repositories_event(action, payload)
                mark_webhook_delivery(delivery_id, "processed")
                return result
            except Exception as e:
                mark_webhook_delivery(delivery_id, "failed", str(e))
                raise

        if event_type == "pull_request":
            if action not in ("opened", "synchronize"):
                if _already_processed(delivery_id, event_type, action, None, None):
                    return {"status": "duplicate", "delivery": delivery_id}
                mark_webhook_delivery(delivery_id, "ignored")
                return {"status": "ignored", "reason": f"pull_request.{action} analiz tetiklemez"}

            owner = repository_data.get("owner", {}).get("login")
            repo_name = repository_data.get("name")
            pr = payload.get("pull_request", {})
            pr_number = pr.get("number")
            head_sha = pr.get("head", {}).get("sha")
            account = payload.get("installation", {}).get("account", {})
            account_login = account.get("login") or owner or "unknown"
            account_type = account.get("type") or repository_data.get("owner", {}).get("type") or "unknown"

            if not all([installation_id, repository_id, owner, repo_name, pr_number, head_sha]):
                if _already_processed(delivery_id, event_type, action, None, None):
                    return {"status": "duplicate", "delivery": delivery_id}
                background_tasks.add_task(_process_pr_event_bg, action, payload, delivery_id, None)
                return {"status": "accepted", "event": "pull_request", "action": action}

            # Establish FK parents before the durable delivery claim.
            ensure_installation(installation_id, account_login=account_login, account_type=account_type)
            repo_row_id = upsert_repository(
                installation_id=installation_id,
                github_repository_id=repository_id,
                owner=owner,
                name=repo_name,
                full_name=repository_data.get("full_name") or f"{owner}/{repo_name}",
            )
            if repo_row_id is None:
                mark_webhook_delivery(delivery_id, "failed", "Repository persistence unavailable")
                raise HTTPException(status_code=503, detail="Repository persistence unavailable")

            if _already_processed(delivery_id, event_type, action, installation_id, repository_id):
                return {"status": "duplicate", "delivery": delivery_id}

            review_run_id = create_review_run(installation_id, repo_row_id, pr_number, head_sha)
            if review_run_id is None:
                mark_webhook_delivery(delivery_id, "failed", "Review run persistence unavailable")
                raise HTTPException(status_code=503, detail="Review run persistence unavailable")

            background_tasks.add_task(_process_pr_event_bg, action, payload, delivery_id, review_run_id)
            return {"status": "accepted", "event": "pull_request", "action": action, "review_run_id": review_run_id}

        if not _already_processed(delivery_id, event_type, action, None, None):
            mark_webhook_delivery(delivery_id, "ignored")
        return {"status": "ignored", "reason": f"'{event_type}' event'i desteklenmiyor"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Webhook hatası: {str(e)}")
        if sentry_sdk is not None:
            sentry_sdk.capture_exception(e)
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
    added_payload = payload.get("repositories_added", [])
    removed_payload = payload.get("repositories_removed", [])
    repos_added = [r.get("full_name") for r in added_payload if r.get("full_name")]
    repos_removed = [r.get("full_name") for r in removed_payload if r.get("full_name")]

    for item in added_payload:
        if item.get("id") and item.get("full_name"):
            full_name = item["full_name"]
            owner_name, repo_name = full_name.split("/", 1)
            upsert_repository(
                installation_id=installation_id,
                github_repository_id=item["id"],
                owner=owner_name,
                name=repo_name,
                full_name=full_name,
                active=True,
            )

    for item in removed_payload:
        if item.get("id"):
            from app.repository import deactivate_repository
            deactivate_repository(installation_id, item["id"])

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


async def _handle_pull_request_event(
    action: str, payload: dict, review_run_id: Optional[int] = None
) -> dict:
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
            elif security.get("partial_scan") and not security.get("has_security_issues"):
                comment += "### ⚠️ Kısmi Güvenlik Taraması\n"
                comment += f"{security.get('partial_message', 'PR’nin tamamı taranmadı.')}\n"
                comment += "Bu nedenle sonuç **tam güvenlik taraması** olarak yorumlanmamalıdır.\n\n"
            elif security.get("has_security_issues"):
                total = len(security.get("vulnerabilities", []))
                comment += "### 🚨 Güvenlik Bulguları (Semgrep + Gemini)\n"
                if security.get("partial_scan"):
                    comment += (
                        "⚠️ **Kısmi tarama:** PR'nin tamamı Semgrep kapsamına girmedi; "
                        "aşağıdaki bulgular yalnızca taranan kapsam içindir.\n\n"
                    )
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
