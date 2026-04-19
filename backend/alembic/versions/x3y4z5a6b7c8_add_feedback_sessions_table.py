"""Add feedback_sessions table

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-04-19
"""
from alembic import op

revision = "x3y4z5a6b7c8"
down_revision = "w2x3y4z5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE feedback_sessions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            category VARCHAR(50),
            severity VARCHAR(20),
            area VARCHAR(100),
            summary TEXT,
            recommendations JSONB,
            transcript JSONB,
            page_url VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_feedback_sessions_user_id ON feedback_sessions(user_id)")
    op.execute("CREATE INDEX ix_feedback_sessions_status ON feedback_sessions(status)")
    op.execute("CREATE INDEX ix_feedback_sessions_created_at ON feedback_sessions(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedback_sessions")
