"""Add investor_rankings and investor_ranking_batch_jobs tables

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "y4z5a6b7c8d9"
down_revision = "x3y4z5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investor_rankings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("investor_id", UUID(as_uuid=True), sa.ForeignKey("investors.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overall_score", sa.Float, nullable=False),
        sa.Column("portfolio_performance", sa.Float, nullable=False),
        sa.Column("deal_activity", sa.Float, nullable=False),
        sa.Column("exit_track_record", sa.Float, nullable=False),
        sa.Column("stage_expertise", sa.Float, nullable=False),
        sa.Column("sector_expertise", sa.Float, nullable=False),
        sa.Column("follow_on_rate", sa.Float, nullable=False),
        sa.Column("network_quality", sa.Float, nullable=False),
        sa.Column("narrative", sa.Text, nullable=False),
        sa.Column("perplexity_research", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scoring_metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_investor_rankings_overall_score", "investor_rankings", ["overall_score"])
    op.create_index("ix_investor_rankings_investor_id", "investor_rankings", ["investor_id"], unique=True)

    op.create_table(
        "investor_ranking_batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total_investors", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("processed_investors", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_investor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("current_investor_name", sa.String(300), nullable=True),
        sa.Column("investors_scored", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("investor_ranking_batch_jobs")
    op.drop_index("ix_investor_rankings_investor_id", table_name="investor_rankings")
    op.drop_index("ix_investor_rankings_overall_score", table_name="investor_rankings")
    op.drop_table("investor_rankings")
