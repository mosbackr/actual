"""Add entity_type column to startups

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE entitytype AS ENUM ('startup', 'fund', 'vehicle', 'unknown')")
    op.add_column(
        "startups",
        sa.Column("entity_type", sa.Enum("startup", "fund", "vehicle", "unknown", name="entitytype"),
                   nullable=False, server_default="startup"),
    )


def downgrade() -> None:
    op.drop_column("startups", "entity_type")
    op.execute("DROP TYPE entitytype")
