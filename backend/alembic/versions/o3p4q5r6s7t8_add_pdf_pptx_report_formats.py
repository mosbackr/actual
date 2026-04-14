"""Add pdf and pptx report formats

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-04-14
"""
from alembic import op

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE reportformat ADD VALUE IF NOT EXISTS 'pdf'")
    op.execute("ALTER TYPE reportformat ADD VALUE IF NOT EXISTS 'pptx'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an ENUM type.
    pass
