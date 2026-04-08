import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Enum, Float, ForeignKey, String, Table, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class StartupStage(str, enum.Enum):
    pre_seed = "pre_seed"
    seed = "seed"
    series_a = "series_a"
    series_b = "series_b"
    series_c = "series_c"
    growth = "growth"


class StartupStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    featured = "featured"


startup_industries = Table(
    "startup_industries",
    Base.metadata,
    Column("startup_id", UUID(as_uuid=True), ForeignKey("startups.id"), primary_key=True),
    Column("industry_id", UUID(as_uuid=True), ForeignKey("industries.id"), primary_key=True),
)


class Startup(Base):
    __tablename__ = "startups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stage: Mapped[StartupStage] = mapped_column(Enum(StartupStage), nullable=False)
    status: Mapped[StartupStatus] = mapped_column(Enum(StartupStatus), nullable=False, default=StartupStatus.pending)
    location_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_country: Mapped[str] = mapped_column(String(100), nullable=False, default="US")
    founded_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    expert_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("due_diligence_templates.id"), nullable=True
    )
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    industries = relationship("Industry", secondary=startup_industries)
