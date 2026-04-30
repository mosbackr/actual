"""Add user_watchlist table

Revision ID: u9v0w1x2y3z4
Revises: t8u9v0w1x2y3
Create Date: 2026-04-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "u9v0w1x2y3z4"
down_revision = "t8u9v0w1x2y3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_watchlist",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("startup_id", UUID(as_uuid=True), sa.ForeignKey("startups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_watchlist_user_id", "user_watchlist", ["user_id"])
    op.create_index("ix_user_watchlist_created_at", "user_watchlist", ["created_at"])
    op.create_unique_constraint("uq_user_watchlist", "user_watchlist", ["user_id", "startup_id"])


def downgrade() -> None:
    op.drop_table("user_watchlist")
