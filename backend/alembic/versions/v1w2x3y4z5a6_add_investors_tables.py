"""Add investors and investor_batch_jobs tables

Revision ID: v1w2x3y4z5a6
Revises: u9v0w1x2y3z4
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "v1w2x3y4z5a6"
down_revision = "u9v0w1x2y3z4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_name", sa.String(300), nullable=False),
        sa.Column("partner_name", sa.String(300), nullable=False),
        sa.Column("email", sa.String(300), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("stage_focus", sa.String(200), nullable=True),
        sa.Column("sector_focus", sa.String(500), nullable=True),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("aum_fund_size", sa.String(100), nullable=True),
        sa.Column("recent_investments", JSON, nullable=True),
        sa.Column("fit_reason", sa.Text, nullable=True),
        sa.Column("source_startups", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("firm_name", "partner_name", name="uq_investor_firm_partner"),
    )
    op.create_index("ix_investors_firm_name", "investors", ["firm_name"])
    op.create_index("ix_investors_sector_focus", "investors", ["sector_focus"])

    op.create_table(
        "investor_batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total_startups", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("processed_startups", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_startup_id", UUID(as_uuid=True), nullable=True),
        sa.Column("current_startup_name", sa.String(300), nullable=True),
        sa.Column("investors_found", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("investor_batch_jobs")
    op.drop_index("ix_investors_sector_focus", table_name="investors")
    op.drop_index("ix_investors_firm_name", table_name="investors")
    op.drop_table("investors")
