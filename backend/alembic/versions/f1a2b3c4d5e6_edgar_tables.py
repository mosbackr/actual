"""EDGAR scraper tables and columns

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("startups", sa.Column("sec_cik", sa.String(20), nullable=True))
    op.add_column("startups", sa.Column("edgar_last_scanned_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "startup_funding_rounds",
        sa.Column("data_source", sa.String(20), nullable=False, server_default="perplexity"),
    )

    op.create_table(
        "edgar_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_mode", sa.Text(), nullable=False, server_default="full"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress_summary", JSON, nullable=False, server_default="{}"),
        sa.Column("current_phase", sa.String(30), nullable=False, server_default="resolving_ciks"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "edgar_job_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("edgar_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("params", JSON, nullable=False, server_default="{}"),
        sa.Column("result", JSON, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_edgar_job_steps_job_id_status", "edgar_job_steps", ["job_id", "status"])


def downgrade() -> None:
    op.drop_table("edgar_job_steps")
    op.drop_table("edgar_jobs")
    op.drop_column("startup_funding_rounds", "data_source")
    op.drop_column("startups", "edgar_last_scanned_at")
    op.drop_column("startups", "sec_cik")
