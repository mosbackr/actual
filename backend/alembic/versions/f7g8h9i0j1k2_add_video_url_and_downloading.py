"""Add video_url column and downloading status

Revision ID: f7g8h9i0j1k2
Revises: e6f7g8h9i0j1
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = "f7g8h9i0j1k2"
down_revision = "e6f7g8h9i0j1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add video_url column
    op.add_column("pitch_sessions", sa.Column("video_url", sa.String(2000), nullable=True))

    # Add 'downloading' to the pitchsessionstatus enum
    op.execute("ALTER TYPE pitchsessionstatus ADD VALUE IF NOT EXISTS 'downloading' BEFORE 'uploading'")


def downgrade() -> None:
    op.drop_column("pitch_sessions", "video_url")
    # Note: PostgreSQL does not support removing enum values
