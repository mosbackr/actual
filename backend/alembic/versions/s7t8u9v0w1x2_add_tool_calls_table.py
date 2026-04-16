"""Add tool_calls table

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL REFERENCES pitch_analyses(id) ON DELETE CASCADE,
            agent_type VARCHAR(100) NOT NULL,
            tool_name VARCHAR(100) NOT NULL,
            input JSONB NOT NULL DEFAULT '{}',
            output JSONB,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tool_calls_analysis_id
        ON tool_calls (analysis_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tool_calls_created_at
        ON tool_calls (analysis_id, created_at)
    """)


def downgrade() -> None:
    op.drop_index("ix_tool_calls_created_at", table_name="tool_calls")
    op.drop_index("ix_tool_calls_analysis_id", table_name="tool_calls")
    op.drop_table("tool_calls")
