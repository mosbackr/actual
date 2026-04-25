"""add investor_faq column to pitch_analyses and pitch_sessions

Revision ID: c3d4e5f6g7h8
Revises: 2b6d7e0b62b0
Create Date: 2026-04-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "c3d4e5f6g7h8"
down_revision = "2b6d7e0b62b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pitch_analyses", sa.Column("investor_faq", JSONB(), nullable=True))
    op.add_column("pitch_sessions", sa.Column("investor_faq", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("pitch_sessions", "investor_faq")
    op.drop_column("pitch_analyses", "investor_faq")
