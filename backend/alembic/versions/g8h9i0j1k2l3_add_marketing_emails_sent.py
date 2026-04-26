"""Add marketing_emails_sent table

Revision ID: g8h9i0j1k2l3
Revises: f7g8h9i0j1k2
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "g8h9i0j1k2l3"
down_revision = "f7g8h9i0j1k2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketing_emails_sent",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("investor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("firm_name", sa.String(300), nullable=False),
        sa.Column("partner_name", sa.String(300), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_marketing_emails_sent_job_id", "marketing_emails_sent", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_marketing_emails_sent_job_id")
    op.drop_table("marketing_emails_sent")
