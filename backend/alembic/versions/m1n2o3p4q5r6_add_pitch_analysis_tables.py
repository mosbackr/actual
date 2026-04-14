"""Add pitch analysis tables

Revision ID: m1n2o3p4q5r6
Revises: g7h8i9j0k1l2
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON, ENUM

revision = "m1n2o3p4q5r6"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None

# Pre-define enum types so they're created once and referenced by name
analysisstatus = ENUM('pending', 'extracting', 'analyzing', 'enriching', 'complete', 'failed', name='analysisstatus', create_type=False)
agenttype = ENUM('problem_solution', 'market_tam', 'traction', 'technology_ip', 'competition_moat', 'team', 'gtm_business_model', 'financials_fundraising', name='agenttype', create_type=False)
reportstatus = ENUM('pending', 'running', 'complete', 'failed', name='reportstatus', create_type=False)
subscriptionstatus = ENUM('none', 'active', 'cancelled', name='subscriptionstatus', create_type=False)


def upgrade() -> None:
    # Create enum types explicitly
    op.execute("DO $$ BEGIN CREATE TYPE analysisstatus AS ENUM ('pending', 'extracting', 'analyzing', 'enriching', 'complete', 'failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE agenttype AS ENUM ('problem_solution', 'market_tam', 'traction', 'technology_ip', 'competition_moat', 'team', 'gtm_business_model', 'financials_fundraising'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE reportstatus AS ENUM ('pending', 'running', 'complete', 'failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE subscriptionstatus AS ENUM ('none', 'active', 'cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    # Add subscription_status column to users
    op.add_column(
        "users",
        sa.Column("subscription_status", subscriptionstatus, nullable=False, server_default="none"),
    )

    # Create pitch_analyses table
    op.create_table(
        "pitch_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_name", sa.String(500), nullable=False),
        sa.Column("status", analysisstatus, nullable=False, server_default="pending"),
        sa.Column("current_agent", sa.String(100), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("fundraising_likelihood", sa.Float(), nullable=True),
        sa.Column("recommended_raise", sa.String(100), nullable=True),
        sa.Column("exit_likelihood", sa.Float(), nullable=True),
        sa.Column("expected_exit_value", sa.String(100), nullable=True),
        sa.Column("expected_exit_timeline", sa.String(100), nullable=True),
        sa.Column("executive_summary", sa.Text(), nullable=True),
        sa.Column("startup_id", UUID(as_uuid=True), sa.ForeignKey("startups.id"), nullable=True),
        sa.Column("publish_consent", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_free_analysis", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create analysis_documents table
    op.create_table(
        "analysis_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("pitch_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("s3_key", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create analysis_reports table
    op.create_table(
        "analysis_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("pitch_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_type", agenttype, nullable=False),
        sa.Column("status", reportstatus, nullable=False, server_default="pending"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column("key_findings", JSON, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("analysis_reports")
    op.drop_table("analysis_documents")
    op.drop_table("pitch_analyses")
    op.drop_column("users", "subscription_status")

    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
    op.execute("DROP TYPE IF EXISTS reportstatus")
    op.execute("DROP TYPE IF EXISTS agenttype")
    op.execute("DROP TYPE IF EXISTS analysisstatus")
