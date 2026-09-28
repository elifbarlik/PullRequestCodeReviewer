"""
SecPR-TR — veri erişim katmanı (Faz 2b).

main.py doğrudan ORM'e dokunmaz; tüm DB işlemleri buradan geçer.
db_enabled() kontrolü tek noktada burada yapılır.

Sözleşme (main._run_semgrep_for_pr deseniyle aynı ilke):
  - DB devre dışıysa her fonksiyon sessizce no-op / None döner.
  - DB açık ama işlem başarısız olursa (bağlantı düştü vb.) exception
    LOGLANIR ve YUTULUR — bir loglama hatası PR yorumunu ya da webhook
    yanıtını asla engellememelidir. Veri kaybı, servis kaybından iyidir.
"""

import logging
from typing import Any, Dict, List, Optional

from app.db import db_enabled, get_session

logger = logging.getLogger(__name__)


def upsert_installation(
    installation_id: int,
    account_login: str,
    account_type: str,
    repository_selection: Optional[str] = None,
) -> None:
    """installation.created → satır oluştur veya güncelle (idempotent)."""
    if not db_enabled():
        return
    try:
        from app.models import Installation

        with get_session() as session:
            inst = session.get(Installation, installation_id)
            if inst is None:
                inst = Installation(
                    id=installation_id,
                    account_login=account_login,
                    account_type=account_type,
                    repository_selection=repository_selection,
                    is_active=True,
                )
                session.add(inst)
            else:
                inst.account_login = account_login
                inst.account_type = account_type
                inst.repository_selection = repository_selection
                inst.is_active = True
        logger.info(f"🗄️  installation kaydedildi: id={installation_id} hesap={account_login}")
    except Exception as e:
        logger.error(f"⚠️  upsert_installation başarısız (yutuldu): {e}")


def ensure_installation(
    installation_id: int,
    account_login: str = "unknown",
    account_type: str = "unknown",
    repository_selection: Optional[str] = None,
) -> bool:
    """
    Installation satırının var olduğunu garanti eder — yoksa oluşturur.

    Neden gerekli: `installation.created` webhook'u kaçırılmış olabilir
    (App, bu DB devreye girmeden önce kurulduysa GitHub o event'i bir daha
    GÖNDERMEZ). Bu durumda ilk `pull_request` event'inde installation
    DB'de bulunmaz ve `usage_logs` INSERT'i ForeignKeyViolation ile patlar.
    Bu fonksiyon PR review akışında `record_usage`'dan ÖNCE çağrılarak
    kaydı lazy olarak açar.

    Var olan bir satırı GÜNCELLEMEZ (account bilgisi zaten doğruysa
    dokunmaya gerek yok, yanlışsa da `installation` event'i düzeltir) —
    sadece eksikse ekler.

    Returns:
        True: satır zaten vardı ya da oluşturuldu | False: DB kapalı / hata
    """
    if not db_enabled():
        return False
    try:
        from app.models import Installation

        with get_session() as session:
            if session.get(Installation, installation_id) is not None:
                return True
            session.add(
                Installation(
                    id=installation_id,
                    account_login=account_login,
                    account_type=account_type,
                    repository_selection=repository_selection,
                    is_active=True,
                )
            )
        logger.info(
            f"🗄️  installation lazy oluşturuldu (created event'i kaçırılmış): "
            f"id={installation_id} hesap={account_login}"
        )
        return True
    except Exception as e:
        logger.error(f"⚠️  ensure_installation başarısız (yutuldu): {e}")
        return False


def deactivate_installation(installation_id: int) -> None:
    """installation.deleted → soft-delete (satır silinmez, is_active=False)."""
    if not db_enabled():
        return
    try:
        from app.models import Installation

        with get_session() as session:
            inst = session.get(Installation, installation_id)
            if inst is not None:
                inst.is_active = False
        logger.info(f"🗄️  installation pasifleştirildi: id={installation_id}")
    except Exception as e:
        logger.error(f"⚠️  deactivate_installation başarısız (yutuldu): {e}")


def update_installation_repos(
    installation_id: int, added: List[str], removed: List[str]
) -> None:
    """
    installation_repositories event'i — şimdilik sadece updated_at dokunuşu
    ve log. Repo erişim listesi tablosu Faz 2c kapsamında.
    """
    if not db_enabled():
        return
    try:
        from app.models import Installation

        with get_session() as session:
            inst = session.get(Installation, installation_id)
            if inst is not None:
                # onupdate=_utcnow'ı tetiklemek için bir alana dokun
                inst.is_active = inst.is_active
        logger.info(
            f"🗄️  installation repo değişikliği loglandı: id={installation_id} "
            f"eklenen={added} çıkarılan={removed}"
        )
    except Exception as e:
        logger.error(f"⚠️  update_installation_repos başarısız (yutuldu): {e}")


def record_usage(
    installation_id: int,
    owner: str,
    repo: str,
    pr_number: int,
    review_types: Optional[List[str]] = None,
    diff_size: int = 0,
    was_truncated: bool = False,
    semgrep_status: Optional[str] = None,
    finding_count: int = 0,
    parse_success: Optional[bool] = None,
    duration_ms: Optional[int] = None,
    t_github_ms: Optional[int] = None,
    t_semgrep_ms: Optional[int] = None,
    t_gemini_ms: Optional[int] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    gemini_cost_usd: Optional[float] = None,
    llm_calls: Optional[int] = None,
    llm_cache_hits: Optional[int] = None,
) -> Optional[int]:
    """
    Bir PR analizini usage_logs'a yazar.

    Returns:
        Oluşturulan usage_log.id, veya DB kapalı/hata durumunda None.
        (id, record_findings'e bağ kurmak için kullanılır)
    """
    if not db_enabled():
        return None
    try:
        from app.models import UsageLog

        with get_session() as session:
            log = UsageLog(
                installation_id=installation_id,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                review_types=list(review_types) if review_types else None,
                diff_size=diff_size,
                was_truncated=was_truncated,
                semgrep_status=semgrep_status,
                finding_count=finding_count,
                parse_success=parse_success,
                duration_ms=duration_ms,
                t_github_ms=t_github_ms,
                t_semgrep_ms=t_semgrep_ms,
                t_gemini_ms=t_gemini_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                gemini_cost_usd=gemini_cost_usd,
                llm_calls=llm_calls,
                llm_cache_hits=llm_cache_hits,
            )
            session.add(log)
            session.flush()  # id'yi al
            usage_log_id = log.id
        logger.info(
            f"🗄️  usage_log yazıldı: id={usage_log_id} {owner}/{repo}#{pr_number} "
            f"semgrep={semgrep_status} bulgu={finding_count} süre={duration_ms}ms"
        )
        return usage_log_id
    except Exception as e:
        logger.error(f"⚠️  record_usage başarısız (yutuldu): {e}")
        return None


def record_findings(
    usage_log_id: Optional[int],
    installation_id: int,
    findings: List[Dict[str, Any]],
) -> None:
    """
    Semgrep bulgularını findings tablosuna yazar.

    Args:
        usage_log_id: record_usage'ın döndürdüğü id. None ise (DB kapalı
                      ya da usage yazılamadı) hiçbir şey yapılmaz.
        findings: semgrep_scanner.scan_diff() çıktısı —
                  [{file, line, rule_id, severity, cwe, ...}, ...]
    """
    if not db_enabled() or usage_log_id is None or not findings:
        return
    try:
        from app.models import Finding

        with get_session() as session:
            for f in findings:
                cwe = f.get("cwe")
                session.add(
                    Finding(
                        usage_log_id=usage_log_id,
                        installation_id=installation_id,
                        file=str(f.get("file", "unknown"))[:1024],
                        line=int(f.get("line", 0) or 0),
                        rule_id=str(f.get("rule_id", "unknown"))[:512],
                        severity=str(f.get("severity", "medium"))[:16],
                        cwe=", ".join(cwe) if isinstance(cwe, (list, tuple)) else (str(cwe) if cwe else None),
                    )
                )
        logger.info(f"🗄️  {len(findings)} finding yazıldı (usage_log={usage_log_id})")
    except Exception as e:
        logger.error(f"⚠️  record_findings başarısız (yutuldu): {e}")


# -------------------------------------------------------------------
# Installation ayarları (Faz 2c — repo/installation bazlı Semgrep config)
# -------------------------------------------------------------------

# DB kapalıyken veya ayar satırı yokken dönülen varsayılan.
# semgrep_configs=None → semgrep_scanner.DEFAULT_SEMGREP_CONFIGS kullanılır.
DEFAULT_INSTALLATION_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "semgrep_configs": None,
}


def get_installation_settings(installation_id: int) -> Dict[str, Any]:
    """
    Bir installation'ın ayarlarını döndürür.

    DB kapalıysa veya ayar satırı yoksa DEFAULT_INSTALLATION_SETTINGS
    döner — yani "hiç ayar yapılmamış" durumu her zaman güvenli varsayılana
    (tarama açık, varsayılan ruleset) düşer.

    Returns:
        {"enabled": bool, "semgrep_configs": list[str] | None}
    """
    if not db_enabled():
        return dict(DEFAULT_INSTALLATION_SETTINGS)
    try:
        from app.models import Settings

        with get_session() as session:
            row = session.get(Settings, installation_id)
            if row is None:
                return dict(DEFAULT_INSTALLATION_SETTINGS)
            configs = row.semgrep_configs
            return {
                "enabled": bool(row.enabled),
                "semgrep_configs": list(configs) if configs else None,
            }
    except Exception as e:
        logger.error(f"⚠️  get_installation_settings başarısız (varsayılana düşülüyor): {e}")
        return dict(DEFAULT_INSTALLATION_SETTINGS)


def set_installation_settings(
    installation_id: int,
    enabled: Optional[bool] = None,
    semgrep_configs: Optional[List[str]] = None,
    _clear_configs: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Bir installation'ın ayarlarını oluşturur/günceller (idempotent).

    Args:
        enabled: verilirse güncellenir; None ise dokunulmaz
        semgrep_configs: verilirse güncellenir (liste); None + _clear_configs=False
                         ise dokunulmaz
        _clear_configs: True ise semgrep_configs açıkça NULL'a çekilir
                        (yani "varsayılan ruleset'e dön")

    Returns:
        Güncel ayar dict'i, veya DB kapalı/hata durumunda None.
    """
    if not db_enabled():
        return None
    try:
        from app.models import Settings

        with get_session() as session:
            row = session.get(Settings, installation_id)
            if row is None:
                row = Settings(installation_id=installation_id)
                session.add(row)
            if enabled is not None:
                row.enabled = enabled
            if _clear_configs:
                row.semgrep_configs = None
            elif semgrep_configs is not None:
                row.semgrep_configs = list(semgrep_configs)
            session.flush()
            result = {
                "enabled": bool(row.enabled),
                "semgrep_configs": list(row.semgrep_configs) if row.semgrep_configs else None,
            }
        logger.info(f"🗄️  installation ayarı güncellendi: id={installation_id} {result}")
        return result
    except Exception as e:
        logger.error(f"⚠️  set_installation_settings başarısız (yutuldu): {e}")
        return None


def check_rate_limit(installation_id: int, limit_per_hour: int = 50) -> bool:
    """Return True when the installation is below its rolling hourly PR-review limit."""
    if limit_per_hour <= 0 or not db_enabled():
        return True
    try:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func, select
        from app.models import UsageLog

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        with get_session() as session:
            count = session.scalar(
                select(func.count())
                .select_from(UsageLog)
                .where(
                    UsageLog.installation_id == installation_id,
                    UsageLog.created_at >= one_hour_ago,
                )
            ) or 0
        return int(count) < int(limit_per_hour)
    except Exception as e:
        # Fail-open for availability: a DB outage must not turn into a GitHub
        # webhook failure or a silent denial of service for legitimate users.
        logger.error(
            f"⚠️  Rate limit kontrolü başarısız (izin veriliyor): {e}"
        )
        return True


def get_detailed_metrics() -> Optional[Dict[str, Any]]:
    """Operational and cost metrics for the dashboard/metrics endpoint."""
    if not db_enabled():
        return None
    try:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func, select
        from app.models import Finding, UsageLog

        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        with get_session() as session:
            reviews_24h = session.scalar(
                select(func.count()).select_from(UsageLog).where(UsageLog.created_at >= day_ago)
            ) or 0
            reviews_7d = session.scalar(
                select(func.count()).select_from(UsageLog).where(UsageLog.created_at >= week_ago)
            ) or 0
            findings_24h = session.scalar(
                select(func.count()).select_from(Finding).where(Finding.created_at >= day_ago)
            ) or 0
            month_cost = session.scalar(
                select(func.coalesce(func.sum(UsageLog.gemini_cost_usd), 0.0))
                .where(UsageLog.created_at >= month_start)
            ) or 0.0
            month_input_tokens = session.scalar(
                select(func.coalesce(func.sum(UsageLog.input_tokens), 0))
                .where(UsageLog.created_at >= month_start)
            ) or 0
            month_output_tokens = session.scalar(
                select(func.coalesce(func.sum(UsageLog.output_tokens), 0))
                .where(UsageLog.created_at >= month_start)
            ) or 0
            cache_hits = session.scalar(
                select(func.coalesce(func.sum(UsageLog.llm_cache_hits), 0))
                .where(UsageLog.created_at >= month_start)
            ) or 0
            llm_calls = session.scalar(
                select(func.coalesce(func.sum(UsageLog.llm_calls), 0))
                .where(UsageLog.created_at >= month_start)
            ) or 0

            recent_rows = session.execute(
                select(
                    UsageLog.duration_ms,
                    UsageLog.t_github_ms,
                    UsageLog.t_semgrep_ms,
                    UsageLog.t_gemini_ms,
                    UsageLog.semgrep_status,
                ).where(UsageLog.created_at >= day_ago)
            ).all()

        durations = sorted(
            int(row.duration_ms)
            for row in recent_rows
            if row.duration_ms is not None
        )

        def _percentile(values: list[int], percentile: float) -> float:
            if not values:
                return 0.0
            if len(values) == 1:
                return float(values[0])
            rank = (len(values) - 1) * percentile
            lower = int(rank)
            upper = min(lower + 1, len(values) - 1)
            weight = rank - lower
            return values[lower] + (values[upper] - values[lower]) * weight

        def _avg(field: str) -> float:
            values = [
                int(getattr(row, field))
                for row in recent_rows
                if getattr(row, field) is not None
            ]
            return round(sum(values) / len(values), 1) if values else 0.0

        review_count_24h = len(recent_rows)
        semgrep_unavailable_24h = sum(
            1 for row in recent_rows if row.semgrep_status == "unavailable"
        )

        return {
            "reviews_last_24h": reviews_24h,
            "reviews_last_7d": reviews_7d,
            "avg_duration_ms_24h": round(sum(durations) / len(durations), 1) if durations else 0.0,
            "p50_duration_ms_24h": round(_percentile(durations, 0.50), 1),
            "p95_duration_ms_24h": round(_percentile(durations, 0.95), 1),
            "avg_timing_ms_24h": {
                "github": _avg("t_github_ms"),
                "semgrep_and_summary": _avg("t_semgrep_ms"),
                "gemini_detail": _avg("t_gemini_ms"),
            },
            "semgrep_unavailable_rate_pct_24h": round(
                (semgrep_unavailable_24h / review_count_24h) * 100, 1
            ) if review_count_24h else 0.0,
            "findings_last_24h": findings_24h,
            "gemini_cost_usd_month": round(float(month_cost), 8),
            "gemini_input_tokens_month": int(month_input_tokens),
            "gemini_output_tokens_month": int(month_output_tokens),
            "llm_calls_month": int(llm_calls),
            "llm_cache_hits_month": int(cache_hits),
            "llm_cache_hit_rate_pct_month": round((cache_hits / llm_calls) * 100, 1) if llm_calls else 0.0,
        }
    except Exception as e:
        logger.error(f"⚠️  get_detailed_metrics başarısız: {e}")
        return None


# -------------------------------------------------------------------
# /stats için okuma yardımcıları
# -------------------------------------------------------------------

def get_stats_summary() -> Optional[Dict[str, Any]]:
    """
    /stats endpoint'i için özet sayaçlar. DB kapalıysa None.
    """
    if not db_enabled():
        return None
    try:
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import func, select

        from app.models import Installation, UsageLog

        with get_session() as session:
            total_installations = session.scalar(
                select(func.count()).select_from(Installation)
            )
            active_installations = session.scalar(
                select(func.count()).select_from(Installation).where(Installation.is_active.is_(True))
            )
            total_reviews = session.scalar(select(func.count()).select_from(UsageLog))
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            reviews_7d = session.scalar(
                select(func.count()).select_from(UsageLog).where(UsageLog.created_at >= week_ago)
            )
        return {
            "installations_total": total_installations or 0,
            "installations_active": active_installations or 0,
            "reviews_total": total_reviews or 0,
            "reviews_last_7d": reviews_7d or 0,
        }
    except Exception as e:
        logger.error(f"⚠️  get_stats_summary başarısız (yutuldu): {e}")
        return None
