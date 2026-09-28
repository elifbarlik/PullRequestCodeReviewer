"""add review cost and timing metrics

Revision ID: 0002_review_cost_metrics
Revises: 0001_baseline_schema
Create Date: 2026-09-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_review_cost_metrics"
down_revision: Union[str, Sequence[str], None] = "0001_baseline_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = [
        ("t_github_ms", sa.Integer()),
        ("t_semgrep_ms", sa.Integer()),
        ("t_gemini_ms", sa.Integer()),
        ("input_tokens", sa.Integer()),
        ("output_tokens", sa.Integer()),
        ("gemini_cost_usd", sa.Float()),
        ("llm_calls", sa.Integer()),
        ("llm_cache_hits", sa.Integer()),
    ]
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("usage_logs")}
    for name, column in columns:
        if name not in existing:
            op.add_column("usage_logs", sa.Column(name, column, nullable=True))


def downgrade() -> None:
    for name in [
        "llm_cache_hits",
        "llm_calls",
        "gemini_cost_usd",
        "output_tokens",
        "input_tokens",
        "t_gemini_ms",
        "t_semgrep_ms",
        "t_github_ms",
    ]:
        op.drop_column("usage_logs", name)
