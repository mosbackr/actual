"""add password_hash and credentials provider

Revision ID: c3a7f1e2d4b5
Revises: 11a1ad5dbefc
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3a7f1e2d4b5"
down_revision: Union[str, None] = "11a1ad5dbefc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add password_hash column
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))

    # Add 'credentials' to the auth provider enum
    op.execute("ALTER TYPE authprovider ADD VALUE IF NOT EXISTS 'credentials'")


def downgrade() -> None:
    op.drop_column("users", "password_hash")
    # Note: PostgreSQL doesn't support removing enum values
