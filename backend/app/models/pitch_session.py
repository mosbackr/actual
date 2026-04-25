import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class PitchSessionStatus(str, enum.Enum):
    uploading = "uploading"
    transcribing = "transcribing"
    labeling = "labeling"
    analyzing = "analyzing"
    complete = "complete"
    failed = "failed"


class PitchAnalysisPhase(str, enum.Enum):
    claim_extraction = "claim_extraction"
    fact_check_founders = "fact_check_founders"
    fact_check_investors = "fact_check_investors"
    conversation_analysis = "conversation_analysis"
    scoring = "scoring"
    benchmark = "benchmark"


class PitchPhaseStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


class PitchSession(Base):
    __tablename__ = "pitch_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    startup_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("startups.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[PitchSessionStatus] = mapped_column(
        Enum(PitchSessionStatus, name="pitchsessionstatus"),
        nullable=False,
        default=PitchSessionStatus.uploading,
    )
    file_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    transcript_labeled: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    benchmark_percentiles: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    investor_faq: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="pitch_sessions")
    results: Mapped[list["PitchAnalysisResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class PitchAnalysisResult(Base):
    __tablename__ = "pitch_analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pitch_sessions.id"), nullable=False)
    phase: Mapped[PitchAnalysisPhase] = mapped_column(
        Enum(PitchAnalysisPhase, name="pitchanalysisphase"), nullable=False,
    )
    status: Mapped[PitchPhaseStatus] = mapped_column(
        Enum(PitchPhaseStatus, name="pitchphasestatus"),
        nullable=False,
        default=PitchPhaseStatus.pending,
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session: Mapped["PitchSession"] = relationship(back_populates="results")


class PitchBenchmark(Base):
    __tablename__ = "pitch_benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    median_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p25: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p75: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    patterns: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
