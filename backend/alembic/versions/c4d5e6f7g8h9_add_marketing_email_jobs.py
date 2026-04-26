"""Add marketing_email_jobs table

Revision ID: c4d5e6f7g8h9
Revises: b2c3d4e5f6a1
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "c4d5e6f7g8h9"
down_revision = "b2c3d4e5f6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketing_email_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("html_template", sa.Text, nullable=False),
        sa.Column("total_recipients", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("sent_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_investor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("current_investor_name", sa.String(300), nullable=True),
        sa.Column("from_address", sa.String(255), nullable=False, server_default=sa.text("'updates@deepthesis.co'")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("marketing_email_jobs")
