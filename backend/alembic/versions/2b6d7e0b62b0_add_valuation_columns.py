"""add valuation and technical review columns to pitch_analyses

Revision ID: 2b6d7e0b62b0
Revises: z5a6b7c8d9e0
Create Date: 2026-04-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "2b6d7e0b62b0"
down_revision = "z5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pitch_analyses", sa.Column("estimated_valuation", sa.String(200), nullable=True))
    op.add_column("pitch_analyses", sa.Column("valuation_justification", sa.Text(), nullable=True))
    op.add_column("pitch_analyses", sa.Column("technical_expert_review", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("pitch_analyses", "technical_expert_review")
    op.drop_column("pitch_analyses", "valuation_justification")
    op.drop_column("pitch_analyses", "estimated_valuation")
