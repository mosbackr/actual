import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class BatchJobType(str, enum.Enum):
    initial = "initial"
    refresh = "refresh"


class BatchJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BatchJobPhase(str, enum.Enum):
    discovering_investors = "discovering_investors"
    finding_startups = "finding_startups"
    enriching = "enriching"
    complete = "complete"


class BatchStepType(str, enum.Enum):
    discover_investors = "discover_investors"
    find_startups = "find_startups"
    add_to_triage = "add_to_triage"
    enrich = "enrich"


class BatchStepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_type: Mapped[BatchJobType] = mapped_column(default=BatchJobType.initial)
    status: Mapped[BatchJobStatus] = mapped_column(default=BatchJobStatus.pending)
    refresh_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_summary: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default=text("'{}'::jsonb")
    )
    current_phase: Mapped[BatchJobPhase] = mapped_column(
        default=BatchJobPhase.discovering_investors
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["BatchJobStep"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class BatchJobStep(Base):
    __tablename__ = "batch_job_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batch_jobs.id", ondelete="CASCADE")
    )
    step_type: Mapped[BatchStepType]
    status: Mapped[BatchStepStatus] = mapped_column(default=BatchStepStatus.pending)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["BatchJob"] = relationship(back_populates="steps")
