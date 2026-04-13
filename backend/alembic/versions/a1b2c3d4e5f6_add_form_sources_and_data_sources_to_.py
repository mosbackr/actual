"""add form_sources and data_sources to startups

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("startups", sa.Column("form_sources", sa.JSON(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("startups", sa.Column("data_sources", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column("startups", "data_sources")
    op.drop_column("startups", "form_sources")
