"""
SecPR-TR — SQLAlchemy ORM modelleri (Faz 2b veri şeması).

Yol haritasındaki tablolar:
  installations  — her GitHub App kurulumu (installation_id → hesap/org)
  usage_logs     — her PR analizi (kullanım takibi + Gemini maliyet kalibrasyonu)
  findings       — her güvenlik bulgusu (ileride false-positive oranı metriği için)
  settings       — repo/installation bazlı ayarlar (Faz 2c; şema hazır, henüz kullanılmıyor)

JSON alanları için SQLAlchemy'nin taşınabilir `JSON` tipi kullanılır —
Postgres'te JSONB'ye, SQLite'ta (test) TEXT'e map'lenir.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Installation(Base):
    __tablename__ = "installations"

    # GitHub'ın installation.id'si — kendi değeri, autoincrement DEĞİL.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    account_login: Mapped[str] = mapped_column(String(255), index=True)
    account_type: Mapped[str] = mapped_column(String(32))  # "User" | "Organization"
    repository_selection: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "all" | "selected"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    usage_logs: Mapped[list["UsageLog"]] = relationship(back_populates="installation")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id"), index=True, nullable=False
    )
    owner: Mapped[str] = mapped_column(String(255))
    repo: Mapped[str] = mapped_column(String(255))
    pr_number: Mapped[int] = mapped_column(Integer)
    review_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    diff_size: Mapped[int] = mapped_column(Integer, default=0)
    was_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    semgrep_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ok|unavailable|error
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    parse_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    installation: Mapped["Installation"] = relationship(back_populates="usage_logs")
    findings: Mapped[list["Finding"]] = relationship(back_populates="usage_log")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usage_log_id: Mapped[int] = mapped_column(
        ForeignKey("usage_logs.id"), index=True, nullable=False
    )
    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id"), index=True, nullable=False
    )
    file: Mapped[str] = mapped_column(String(1024))
    line: Mapped[int] = mapped_column(Integer, default=0)
    rule_id: Mapped[str] = mapped_column(String(512))
    severity: Mapped[str] = mapped_column(String(16))  # critical|high|medium|low
    cwe: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    usage_log: Mapped["UsageLog"] = relationship(back_populates="findings")


class Settings(Base):
    """Faz 2c için şema — bu turda yazılmıyor, sadece tablo hazır."""

    __tablename__ = "settings"

    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id"), primary_key=True, autoincrement=False
    )
    semgrep_configs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
