"""Add pitch intelligence tables

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "w2x3y4z5a6b7"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute(
        "DO $$ BEGIN CREATE TYPE pitchsessionstatus AS ENUM "
        "('uploading', 'transcribing', 'labeling', 'analyzing', 'complete', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE pitchanalysisphase AS ENUM "
        "('claim_extraction', 'fact_check_founders', 'fact_check_investors', "
        "'conversation_analysis', 'scoring', 'benchmark'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE pitchphasestatus AS ENUM "
        "('pending', 'running', 'complete', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    pitchsessionstatus = sa.Enum(
        'uploading', 'transcribing', 'labeling', 'analyzing', 'complete', 'failed',
        name='pitchsessionstatus', create_type=False,
    )
    pitchanalysisphase = sa.Enum(
        'claim_extraction', 'fact_check_founders', 'fact_check_investors',
        'conversation_analysis', 'scoring', 'benchmark',
        name='pitchanalysisphase', create_type=False,
    )
    pitchphasestatus = sa.Enum(
        'pending', 'running', 'complete', 'failed',
        name='pitchphasestatus', create_type=False,
    )

    op.create_table(
        "pitch_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("startup_id", UUID(as_uuid=True), sa.ForeignKey("startups.id"), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("status", pitchsessionstatus, nullable=False, server_default="uploading"),
        sa.Column("file_url", sa.String(1000), nullable=True),
        sa.Column("file_duration_seconds", sa.Integer, nullable=True),
        sa.Column("transcript_raw", JSON, nullable=True),
        sa.Column("transcript_labeled", JSON, nullable=True),
        sa.Column("scores", JSON, nullable=True),
        sa.Column("benchmark_percentiles", JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "pitch_analysis_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("pitch_sessions.id"), nullable=False),
        sa.Column("phase", pitchanalysisphase, nullable=False),
        sa.Column("status", pitchphasestatus, nullable=False, server_default="pending"),
        sa.Column("result", JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "pitch_benchmarks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("stage", sa.String(50), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("sample_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mean_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("median_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("p25", sa.Float, nullable=False, server_default="0"),
        sa.Column("p75", sa.Float, nullable=False, server_default="0"),
        sa.Column("patterns", JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_pitch_sessions_user_id", "pitch_sessions", ["user_id"])
    op.create_index("ix_pitch_sessions_status", "pitch_sessions", ["status"])
    op.create_index("ix_pitch_analysis_results_session_id", "pitch_analysis_results", ["session_id"])
    op.create_index("ix_pitch_benchmarks_dimension_stage", "pitch_benchmarks", ["dimension", "stage", "industry"])


def downgrade() -> None:
    op.drop_table("pitch_analysis_results")
    op.drop_table("pitch_sessions")
    op.drop_table("pitch_benchmarks")
    op.execute("DROP TYPE IF EXISTS pitchphasestatus")
    op.execute("DROP TYPE IF EXISTS pitchanalysisphase")
    op.execute("DROP TYPE IF EXISTS pitchsessionstatus")
