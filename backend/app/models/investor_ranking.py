import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base
from app.models.investor import BatchJobStatus


class InvestorRanking(Base):
    __tablename__ = "investor_rankings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investors.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    portfolio_performance: Mapped[float] = mapped_column(Float, nullable=False)
    deal_activity: Mapped[float] = mapped_column(Float, nullable=False)
    exit_track_record: Mapped[float] = mapped_column(Float, nullable=False)
    stage_expertise: Mapped[float] = mapped_column(Float, nullable=False)
    sector_expertise: Mapped[float] = mapped_column(Float, nullable=False)
    follow_on_rate: Mapped[float] = mapped_column(Float, nullable=False)
    network_quality: Mapped[float] = mapped_column(Float, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    perplexity_research: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scoring_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class InvestorRankingBatchJob(Base):
    __tablename__ = "investor_ranking_batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchJobStatus.pending.value
    )
    total_investors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_investors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_investor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_investor_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    investors_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
