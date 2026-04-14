"""Add analyst tables

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON, ENUM

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None

messagerole = ENUM("user", "assistant", name="messagerole", create_type=False)
reportformat = ENUM("docx", "xlsx", name="reportformat", create_type=False)
reportgenstatus = ENUM(
    "pending", "generating", "complete", "failed", name="reportgenstatus", create_type=False
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE messagerole AS ENUM ('user', 'assistant'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE reportformat AS ENUM ('docx', 'xlsx'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE reportgenstatus AS ENUM ('pending', 'generating', 'complete', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "analyst_conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default="New Conversation"),
        sa.Column("share_token", sa.String(64), unique=True, nullable=True),
        sa.Column("is_free_conversation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "analyst_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", messagerole, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("charts", JSON, nullable=True),
        sa.Column("citations", JSON, nullable=True),
        sa.Column("context_startups", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "analyst_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("format", reportformat, nullable=False),
        sa.Column("status", reportgenstatus, nullable=False, server_default="pending"),
        sa.Column("s3_key", sa.String(1000), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("analyst_reports")
    op.drop_table("analyst_messages")
    op.drop_table("analyst_conversations")

    op.execute("DROP TYPE IF EXISTS reportgenstatus")
    op.execute("DROP TYPE IF EXISTS reportformat")
    op.execute("DROP TYPE IF EXISTS messagerole")
