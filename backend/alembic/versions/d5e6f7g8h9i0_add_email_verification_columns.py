"""Add email verification columns to investors

Revision ID: d5e6f7g8h9i0
Revises: c4d5e6f7g8h9
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7g8h9i0"
down_revision = "c4d5e6f7g8h9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investors", sa.Column("email_status", sa.String(20), nullable=False, server_default=sa.text("'unverified'")))
    op.add_column("investors", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("investors", sa.Column("email_unsubscribed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("investors", sa.Column("email_unsubscribed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("investors", "email_unsubscribed_at")
    op.drop_column("investors", "email_unsubscribed")
    op.drop_column("investors", "email_verified_at")
    op.drop_column("investors", "email_status")
