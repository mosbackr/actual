"""add public stage to startupstage enum

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-12

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE startupstage ADD VALUE IF NOT EXISTS 'public'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enums easily.
    # A full migration would require creating a new type, migrating data, and swapping.
    pass
