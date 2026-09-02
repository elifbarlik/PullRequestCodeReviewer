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
