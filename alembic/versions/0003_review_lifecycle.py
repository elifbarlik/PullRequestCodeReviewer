"""add repository review lifecycle and webhook delivery persistence
Revision ID: 0003_review_lifecycle
Revises: 0002_review_cost_metrics
Create Date: 2026-09-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003_review_lifecycle"
down_revision: Union[str, Sequence[str], None] = "0002_review_cost_metrics"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "repositories" not in tables:
        op.create_table(
            "repositories",
            sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("installation_id", sa.Integer(), nullable=False),
            sa.Column("owner", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(511), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("full_name"),
        )
        op.create_index("ix_repositories_installation_id", "repositories", ["installation_id"])
        op.create_index("ix_repositories_full_name", "repositories", ["full_name"], unique=True)
    if "review_runs" not in tables:
        op.create_table(
            "review_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("installation_id", sa.Integer(), nullable=False),
            sa.Column("repository_id", sa.Integer(), nullable=False),
            sa.Column("pr_number", sa.Integer(), nullable=False),
            sa.Column("head_sha", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("files_scanned", sa.Integer(), nullable=True),
            sa.Column("findings_count", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("repository_id", "pr_number", "head_sha", name="uq_review_runs_repo_pr_sha"),
        )
        op.create_index("ix_review_runs_installation_id", "review_runs", ["installation_id"])
        op.create_index("ix_review_runs_repository_id", "review_runs", ["repository_id"])
    if "webhook_deliveries" not in tables:
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("delivery_id", sa.String(255), nullable=False),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("action", sa.String(64), nullable=True),
            sa.Column("installation_id", sa.Integer(), nullable=True),
            sa.Column("repository_id", sa.Integer(), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="received"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("delivery_id"),
        )
        op.create_index("ix_webhook_deliveries_delivery_id", "webhook_deliveries", ["delivery_id"], unique=True)
        op.create_index("ix_webhook_deliveries_installation_id", "webhook_deliveries", ["installation_id"])
        op.create_index("ix_webhook_deliveries_repository_id", "webhook_deliveries", ["repository_id"])

def downgrade() -> None:
    for table in ("webhook_deliveries", "review_runs", "repositories"):
        op.drop_table(table)
