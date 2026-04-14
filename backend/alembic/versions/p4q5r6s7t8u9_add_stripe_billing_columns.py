"""Add Stripe billing columns to users

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add past_due to subscription status enum
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'past_due'")

    # Create subscription tier enum
    op.execute(
        "DO $$ BEGIN CREATE TYPE subscriptiontier AS ENUM ('starter', 'professional', 'unlimited'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # Add Stripe columns to users table
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), unique=True, nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "subscription_tier",
            sa.Enum("starter", "professional", "unlimited", name="subscriptiontier", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("users", sa.Column("subscription_period_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "subscription_period_end")
    op.drop_column("users", "subscription_tier")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.execute("DROP TYPE IF EXISTS subscriptiontier")
