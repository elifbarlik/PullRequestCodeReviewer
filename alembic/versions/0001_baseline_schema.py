"""baseline schema

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-09-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0001_baseline_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # Existing MVP databases keep their data: baseline only creates tables
    # that do not exist yet. This makes the first deployment non-destructive.
    if not _has_table("installations"):
        op.create_table(
            "installations",
            sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("account_login", sa.String(length=255), nullable=False),
            sa.Column("account_type", sa.String(length=32), nullable=False),
            sa.Column("repository_selection", sa.String(length=16), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_installations_account_login", "installations", ["account_login"], unique=False)

    if not _has_table("usage_logs"):
        op.create_table(
            "usage_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("installation_id", sa.Integer(), nullable=False),
            sa.Column("owner", sa.String(length=255), nullable=False),
            sa.Column("repo", sa.String(length=255), nullable=False),
            sa.Column("pr_number", sa.Integer(), nullable=False),
            sa.Column("review_types", sa.JSON(), nullable=True),
            sa.Column("diff_size", sa.Integer(), nullable=False),
            sa.Column("was_truncated", sa.Boolean(), nullable=False),
            sa.Column("semgrep_status", sa.String(length=16), nullable=True),
            sa.Column("finding_count", sa.Integer(), nullable=False),
            sa.Column("parse_success", sa.Boolean(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("t_github_ms", sa.Integer(), nullable=True),
            sa.Column("t_semgrep_ms", sa.Integer(), nullable=True),
            sa.Column("t_gemini_ms", sa.Integer(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("gemini_cost_usd", sa.Float(), nullable=True),
            sa.Column("llm_calls", sa.Integer(), nullable=True),
            sa.Column("llm_cache_hits", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_usage_logs_installation_id", "usage_logs", ["installation_id"], unique=False)
        op.create_index("ix_usage_logs_created_at", "usage_logs", ["created_at"], unique=False)

    if not _has_table("findings"):
        op.create_table(
            "findings",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("usage_log_id", sa.Integer(), nullable=False),
            sa.Column("installation_id", sa.Integer(), nullable=False),
            sa.Column("file", sa.String(length=1024), nullable=False),
            sa.Column("line", sa.Integer(), nullable=False),
            sa.Column("rule_id", sa.String(length=512), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("cwe", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
            sa.ForeignKeyConstraint(["usage_log_id"], ["usage_logs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_findings_usage_log_id", "findings", ["usage_log_id"], unique=False)
        op.create_index("ix_findings_installation_id", "findings", ["installation_id"], unique=False)

    if not _has_table("settings"):
        op.create_table(
            "settings",
            sa.Column("installation_id", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("semgrep_configs", sa.JSON(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
            sa.PrimaryKeyConstraint("installation_id"),
        )


def downgrade() -> None:
    # Development-only rollback. Production migrations should be additive.
    if _has_table("settings"):
        op.drop_table("settings")
    if _has_table("findings"):
        op.drop_index("ix_findings_installation_id", table_name="findings")
        op.drop_index("ix_findings_usage_log_id", table_name="findings")
        op.drop_table("findings")
    if _has_table("usage_logs"):
        op.drop_index("ix_usage_logs_created_at", table_name="usage_logs")
        op.drop_index("ix_usage_logs_installation_id", table_name="usage_logs")
        op.drop_table("usage_logs")
    if _has_table("installations"):
        op.drop_index("ix_installations_account_login", table_name="installations")
        op.drop_table("installations")
