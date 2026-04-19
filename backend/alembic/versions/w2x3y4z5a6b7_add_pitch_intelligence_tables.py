"""Add pitch intelligence tables

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-04-19
"""
from alembic import op

revision = "w2x3y4z5a6b7"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE pitchsessionstatus AS ENUM "
        "('uploading', 'transcribing', 'labeling', 'analyzing', 'complete', 'failed')"
    )
    op.execute(
        "CREATE TYPE pitchanalysisphase AS ENUM "
        "('claim_extraction', 'fact_check_founders', 'fact_check_investors', "
        "'conversation_analysis', 'scoring', 'benchmark')"
    )
    op.execute(
        "CREATE TYPE pitchphasestatus AS ENUM "
        "('pending', 'running', 'complete', 'failed')"
    )
    op.execute("""
        CREATE TABLE pitch_sessions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            startup_id UUID REFERENCES startups(id),
            title VARCHAR(500),
            status pitchsessionstatus NOT NULL DEFAULT 'uploading',
            file_url VARCHAR(1000),
            file_duration_seconds INTEGER,
            transcript_raw JSONB,
            transcript_labeled JSONB,
            scores JSONB,
            benchmark_percentiles JSONB,
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE pitch_analysis_results (
            id UUID PRIMARY KEY,
            session_id UUID NOT NULL REFERENCES pitch_sessions(id),
            phase pitchanalysisphase NOT NULL,
            status pitchphasestatus NOT NULL DEFAULT 'pending',
            result JSONB,
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE pitch_benchmarks (
            id UUID PRIMARY KEY,
            dimension VARCHAR(100) NOT NULL,
            stage VARCHAR(50),
            industry VARCHAR(100),
            sample_count INTEGER NOT NULL DEFAULT 0,
            mean_score FLOAT NOT NULL DEFAULT 0,
            median_score FLOAT NOT NULL DEFAULT 0,
            p25 FLOAT NOT NULL DEFAULT 0,
            p75 FLOAT NOT NULL DEFAULT 0,
            patterns JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_pitch_sessions_user_id ON pitch_sessions(user_id)")
    op.execute("CREATE INDEX ix_pitch_sessions_status ON pitch_sessions(status)")
    op.execute("CREATE INDEX ix_pitch_analysis_results_session_id ON pitch_analysis_results(session_id)")
    op.execute("CREATE INDEX ix_pitch_benchmarks_dimension_stage ON pitch_benchmarks(dimension, stage, industry)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pitch_analysis_results")
    op.execute("DROP TABLE IF EXISTS pitch_sessions")
    op.execute("DROP TABLE IF EXISTS pitch_benchmarks")
    op.execute("DROP TYPE IF EXISTS pitchphasestatus")
    op.execute("DROP TYPE IF EXISTS pitchanalysisphase")
    op.execute("DROP TYPE IF EXISTS pitchsessionstatus")
