import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class BatchJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class Investor(Base):
    __tablename__ = "investors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    firm_name: Mapped[str] = mapped_column(String(300), nullable=False)
    partner_name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str | None] = mapped_column(String(300), nullable=True)
    email_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'unverified'")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_unsubscribed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    email_unsubscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stage_focus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sector_focus: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    aum_fund_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recent_investments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    fit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_startups: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc)
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    __table_args__ = (
        UniqueConstraint("firm_name", "partner_name", name="uq_investor_firm_partner"),
    )


class InvestorBatchJob(Base):
    __tablename__ = "investor_batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchJobStatus.pending.value
    )
    total_startups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_startups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_startup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_startup_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    investors_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
