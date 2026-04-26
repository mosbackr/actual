"""Add investor role to userrole enum

Revision ID: b2c3d4e5f6a1
Revises: c3d4e5f6g7h8
Create Date: 2026-04-25
"""
from alembic import op

revision = "b2c3d4e5f6a1"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'investor'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; no-op
    pass
