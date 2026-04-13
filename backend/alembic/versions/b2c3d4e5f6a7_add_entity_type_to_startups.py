"""add entity_type to startups

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    entity_type_enum = sa.Enum("startup", "fund", "vehicle", "unknown", name="entitytype")
    entity_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "startups",
        sa.Column("entity_type", entity_type_enum, server_default="unknown", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("startups", "entity_type")
    sa.Enum(name="entitytype").drop(op.get_bind(), checkfirst=True)
