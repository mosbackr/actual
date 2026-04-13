import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class EdgarJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EdgarJobPhase(str, enum.Enum):
    resolving_ciks = "resolving_ciks"
    fetching_filings = "fetching_filings"
    processing_filings = "processing_filings"
    complete = "complete"


class EdgarStepType(str, enum.Enum):
    resolve_cik = "resolve_cik"
    fetch_filings = "fetch_filings"
    process_filing = "process_filing"


class EdgarStepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class EdgarJob(Base):
    __tablename__ = "edgar_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_mode: Mapped[str] = mapped_column(Text, default="full")
    status: Mapped[EdgarJobStatus] = mapped_column(default=EdgarJobStatus.pending)
    progress_summary: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default=text("'{}'::jsonb")
    )
    current_phase: Mapped[EdgarJobPhase] = mapped_column(
        default=EdgarJobPhase.resolving_ciks
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["EdgarJobStep"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class EdgarJobStep(Base):
    __tablename__ = "edgar_job_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("edgar_jobs.id", ondelete="CASCADE")
    )
    step_type: Mapped[EdgarStepType]
    status: Mapped[EdgarStepStatus] = mapped_column(default=EdgarStepStatus.pending)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["EdgarJob"] = relationship(back_populates="steps")
