"""Add investment_memos table

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "r6s7t8u9v0w1"
down_revision = "q5r6s7t8u9v0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE memostatus AS ENUM (
                'pending', 'researching', 'generating', 'formatting', 'complete', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS investment_memos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL UNIQUE REFERENCES pitch_analyses(id) ON DELETE CASCADE,
            status memostatus NOT NULL DEFAULT 'pending',
            content TEXT,
            s3_key_pdf VARCHAR(1000),
            s3_key_docx VARCHAR(1000),
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_investment_memos_analysis_id
        ON investment_memos (analysis_id)
    """)


def downgrade() -> None:
    op.drop_index("ix_investment_memos_analysis_id", table_name="investment_memos")
    op.drop_table("investment_memos")
    op.execute("DROP TYPE IF EXISTS memostatus")
