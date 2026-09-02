"""
SecPR-TR — veritabanı bağlantı katmanı (Faz 2b: çok kiracılı veri katmanı).

Tasarım kararı: DB opsiyoneldir. `DATABASE_URL` tanımlı değilse tüm veri
katmanı sessizce devre dışı kalır ve uygulama (webhook analizi, /local-review,
testler) bugünkü gibi çalışmaya devam eder. Bu sayede:
  - CI / offline ortamda Postgres kurmaya gerek yok (testler SQLite in-memory kullanır)
  - `/local-review` gibi installation'sız akışlar DB olmadan çalışır
  - DB geçici olarak düşse bile PR yorumu gönderilmeye devam eder (bkz. repository.py)

Lazy-init deseni reviewer._get_gemini_client() ile aynı: engine ilk
ihtiyaç anında kurulur, import anında DATABASE_URL zorunlu değildir.
"""

import logging
import os
from contextlib import contextmanager
from typing import Iterator, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _database_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL", "").strip()
    return url or None


def db_enabled() -> bool:
    """DATABASE_URL tanımlıysa True — çağrı yerleri bununla korunur."""
    return _database_url() is not None


def get_engine():
    """
    SQLAlchemy engine'i lazy oluşturur ve cache'ler.

    Returns:
        Engine, veya DATABASE_URL yoksa None.
    """
    global _engine
    if _engine is not None:
        return _engine

    url = _database_url()
    if url is None:
        return None

    from sqlalchemy import create_engine

    # pool_pre_ping: uzun süre boşta kalan bağlantıların (Postgres idle
    # timeout / ağ kesintisi) sessizce ölmesine karşı koruma.
    _engine = create_engine(url, pool_pre_ping=True, future=True)
    logger.info(f"🗄️  DB engine kuruldu: {url.split('@')[-1] if '@' in url else url}")
    return _engine


def _get_session_factory():
    global _SessionLocal
    if _SessionLocal is not None:
        return _SessionLocal

    engine = get_engine()
    if engine is None:
        return None

    from sqlalchemy.orm import sessionmaker

    _SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return _SessionLocal


@contextmanager
def get_session() -> Iterator[object]:
    """
    Transactional session context manager.

    Kullanım:
        with get_session() as session:
            session.add(obj)
        # buraya gelindiğinde commit edilmiş olur

    DB kapalıysa ValueError fırlatır — çağrı yerleri önce db_enabled()
    kontrol etmeli (repository.py bunu yapar).
    """
    factory = _get_session_factory()
    if factory is None:
        raise ValueError("DB devre dışı (DATABASE_URL yok) — get_session çağrılamaz")

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> bool:
    """
    Tabloları oluşturur (yoksa). Uygulama startup'ında çağrılır.

    Basit `create_all` yaklaşımı — MVP için yeterli. Şema evrilmeye
    başladığında Alembic migration'larına geçilecek (requirements.txt'te
    alembic zaten var).

    Returns:
        True: tablolar hazır | False: DB devre dışı
    """
    engine = get_engine()
    if engine is None:
        logger.info("ℹ️  DB devre dışı — DATABASE_URL tanımlı değil, veri katmanı atlanıyor")
        return False

    from app.models import Base

    Base.metadata.create_all(engine)
    logger.info("✅ DB tabloları hazır (installations, usage_logs, findings, settings)")
    return True


def _reset_for_tests(engine=None, session_factory=None) -> None:
    """
    Sadece testler için — modül seviyesi cache'i sıfırlar ki her test
    kendi in-memory SQLite engine'ini enjekte edebilsin.
    """
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = session_factory
