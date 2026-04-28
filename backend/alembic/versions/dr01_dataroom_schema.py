"""add dataroom tables

Revision ID: dr01
Revises: disc01, h9i0j1k2l3m4
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "dr01"
down_revision = ("disc01", "h9i0j1k2l3m4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create DataroomStatus enum via raw SQL
    op.execute(
        "CREATE TYPE dataroomstatus AS ENUM "
        "('pending', 'uploading', 'submitted', 'analyzing', 'complete', 'expired')"
    )

    # Create dataroom_requests table — use sa.String for status to avoid sa.Enum auto-creation
    op.create_table(
        "dataroom_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("investor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("founder_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("founder_email", sa.String(300), nullable=False),
        sa.Column("founder_name", sa.String(300), nullable=True),
        sa.Column("company_name", sa.String(300), nullable=True),
        sa.Column("personal_message", sa.Text, nullable=True),
        sa.Column("share_token", sa.String(64), unique=True, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("pitch_analyses.id"), nullable=True),
        sa.Column("custom_criteria", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dataroom_requests_investor_id", "dataroom_requests", ["investor_id"])
    op.create_index("ix_dataroom_requests_share_token", "dataroom_requests", ["share_token"], unique=True)

    # Set the proper enum type on the status column
    op.execute("ALTER TABLE dataroom_requests ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE dataroom_requests "
        "ALTER COLUMN status TYPE dataroomstatus USING status::dataroomstatus"
    )
    op.execute("ALTER TABLE dataroom_requests ALTER COLUMN status SET DEFAULT 'pending'")

    # Create dataroom_documents table
    op.create_table(
        "dataroom_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataroom_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("dataroom_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("s3_key", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_dataroom_documents_request_id", "dataroom_documents", ["dataroom_request_id"])

    # Create dataroom_section_reviews table
    op.create_table(
        "dataroom_section_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataroom_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("dataroom_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("criteria_description", sa.Text, nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("findings", JSON, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_dataroom_section_reviews_request_id", "dataroom_section_reviews", ["dataroom_request_id"])

    # Add new notification types
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'dataroom_submitted'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'dataroom_complete'")


def downgrade() -> None:
    op.drop_table("dataroom_section_reviews")
    op.drop_table("dataroom_documents")
    op.drop_table("dataroom_requests")
    sa.Enum(name="dataroomstatus").drop(op.get_bind(), checkfirst=True)
