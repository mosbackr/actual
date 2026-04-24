import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    extracting = "extracting"
    analyzing = "analyzing"
    enriching = "enriching"
    complete = "complete"
    failed = "failed"


class AgentType(str, enum.Enum):
    problem_solution = "problem_solution"
    market_tam = "market_tam"
    traction = "traction"
    technology_ip = "technology_ip"
    competition_moat = "competition_moat"
    team = "team"
    gtm_business_model = "gtm_business_model"
    financials_fundraising = "financials_fundraising"


class ReportStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


class PitchAnalysis(Base):
    __tablename__ = "pitch_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[AnalysisStatus] = mapped_column(default=AnalysisStatus.pending)
    current_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundraising_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_raise: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exit_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_exit_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_exit_timeline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_valuation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    valuation_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_expert_review: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    startup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id"), nullable=True
    )
    publish_consent: Mapped[bool] = mapped_column(Boolean, default=True)
    is_free_analysis: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents: Mapped[list["AnalysisDocument"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    reports: Mapped[list["AnalysisReport"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    memo: Mapped["InvestmentMemo | None"] = relationship(
        back_populates="analysis", uselist=False, cascade="all, delete-orphan"
    )


class AnalysisDocument(Base):
    __tablename__ = "analysis_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pitch_analyses.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped["PitchAnalysis"] = relationship(back_populates="documents")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pitch_analyses.id", ondelete="CASCADE")
    )
    agent_type: Mapped[AgentType] = mapped_column(nullable=False)
    status: Mapped[ReportStatus] = mapped_column(default=ReportStatus.pending)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_findings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis: Mapped["PitchAnalysis"] = relationship(back_populates="reports")
