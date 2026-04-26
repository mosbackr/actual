"""add zoom_connections table and pitch_session zoom columns

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "h9i0j1k2l3m4"
down_revision = "g8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zoom_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("zoom_account_id", sa.String(255), unique=True, nullable=False),
        sa.Column("zoom_email", sa.String(500), nullable=True),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column("pitch_sessions", sa.Column("source", sa.String(50), nullable=True))
    op.add_column("pitch_sessions", sa.Column("zoom_meeting_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("pitch_sessions", "zoom_meeting_id")
    op.drop_column("pitch_sessions", "source")
    op.drop_table("zoom_connections")
