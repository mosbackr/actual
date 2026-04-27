"""Add startup discovery schema — extend startups, startup_founders, create discovery_batch_jobs

Revision ID: disc01
Revises: zav1zoom2avail3
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "disc01"
down_revision = "zav1zoom2avail3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'discovered' to StartupStatus enum
    op.execute("ALTER TYPE startupstatus ADD VALUE IF NOT EXISTS 'discovered'")

    # Add ClassificationStatus enum
    op.execute(
        "CREATE TYPE classificationstatus AS ENUM ('unclassified', 'startup', 'not_startup', 'uncertain')"
    )

    # Add discovery columns to startups
    op.add_column("startups", sa.Column("discovery_source", sa.String(50), nullable=True))
    op.add_column("startups", sa.Column("delaware_corp_name", sa.String(300), nullable=True))
    op.add_column("startups", sa.Column("delaware_file_number", sa.String(50), nullable=True))
    op.add_column("startups", sa.Column("delaware_filed_at", sa.Date, nullable=True))
    op.add_column(
        "startups",
        sa.Column(
            "classification_status",
            sa.Enum("unclassified", "startup", "not_startup", "uncertain", name="classificationstatus", create_type=False),
            nullable=False,
            server_default="unclassified",
        ),
    )
    op.add_column("startups", sa.Column("classification_metadata", JSON, nullable=True))
    op.create_index("ix_startups_delaware_file_number", "startups", ["delaware_file_number"], unique=True)
    op.create_index("ix_startups_classification_status", "startups", ["classification_status"])
    op.create_index("ix_startups_discovery_source", "startups", ["discovery_source"])

    # Add Proxycurl fields to startup_founders
    op.add_column("startup_founders", sa.Column("headline", sa.String(500), nullable=True))
    op.add_column("startup_founders", sa.Column("location", sa.String(300), nullable=True))
    op.add_column("startup_founders", sa.Column("profile_photo_url", sa.String(500), nullable=True))
    op.add_column("startup_founders", sa.Column("work_history", JSON, nullable=True))
    op.add_column("startup_founders", sa.Column("education_history", JSON, nullable=True))
    op.add_column("startup_founders", sa.Column("proxycurl_raw", JSON, nullable=True))

    # Create discovery_batch_jobs table
    op.create_table(
        "discovery_batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("total_items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("processed_items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_item_name", sa.String(300), nullable=True),
        sa.Column("items_created", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("discovery_batch_jobs")

    op.drop_index("ix_startups_discovery_source", table_name="startups")
    op.drop_index("ix_startups_classification_status", table_name="startups")
    op.drop_index("ix_startups_delaware_file_number", table_name="startups")
    op.drop_column("startups", "classification_metadata")
    op.drop_column("startups", "classification_status")
    op.drop_column("startups", "delaware_filed_at")
    op.drop_column("startups", "delaware_file_number")
    op.drop_column("startups", "delaware_corp_name")
    op.drop_column("startups", "discovery_source")

    op.drop_column("startup_founders", "proxycurl_raw")
    op.drop_column("startup_founders", "education_history")
    op.drop_column("startup_founders", "work_history")
    op.drop_column("startup_founders", "profile_photo_url")
    op.drop_column("startup_founders", "location")
    op.drop_column("startup_founders", "headline")

    op.execute("DROP TYPE IF EXISTS classificationstatus")
