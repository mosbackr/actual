"""add zoom_available status to pitchsessionstatus enum

Revision ID: zav1zoom2avail3
Revises: z5a6b7c8d9e0
Create Date: 2026-04-26
"""
from alembic import op

revision = "zav1zoom2avail3"
down_revision = "z5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE pitchsessionstatus ADD VALUE IF NOT EXISTS 'zoom_available' BEFORE 'downloading'")


def downgrade() -> None:
    pass
