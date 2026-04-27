import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Enum, Float, ForeignKey, String, Table, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class StartupStage(str, enum.Enum):
    pre_seed = "pre_seed"
    seed = "seed"
    series_a = "series_a"
    series_b = "series_b"
    series_c = "series_c"
    growth = "growth"
    public = "public"


class StartupStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    featured = "featured"
    discovered = "discovered"


class CompanyStatus(str, enum.Enum):
    active = "active"
    acquired = "acquired"
    ipo = "ipo"
    defunct = "defunct"
    unknown = "unknown"


class EntityType(str, enum.Enum):
    startup = "startup"
    fund = "fund"
    vehicle = "vehicle"
    unknown = "unknown"


class EnrichmentStatus(str, enum.Enum):
    none = "none"
    running = "running"
    complete = "complete"
    failed = "failed"


class ClassificationStatus(str, enum.Enum):
    unclassified = "unclassified"
    startup = "startup"
    not_startup = "not_startup"
    uncertain = "uncertain"


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

    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_funding: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employee_count: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    crunchbase_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    competitors: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    hiring_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    patents: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_metrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_status: Mapped[CompanyStatus] = mapped_column(
        Enum(CompanyStatus), nullable=False, default=CompanyStatus.unknown, server_default="unknown"
    )
    revenue_estimate: Mapped[str | None] = mapped_column(String(200), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enrichment_status: Mapped[EnrichmentStatus] = mapped_column(
        Enum(EnrichmentStatus), nullable=False, default=EnrichmentStatus.none, server_default="none"
    )
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType), nullable=False, default=EntityType.unknown, server_default="unknown"
    )
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sec_cik: Mapped[str | None] = mapped_column(String(20), nullable=True)
    edgar_last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_sources: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    data_sources: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    discovery_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delaware_corp_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    delaware_file_number: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    delaware_filed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    classification_status: Mapped[ClassificationStatus] = mapped_column(
        Enum(ClassificationStatus), nullable=False, default=ClassificationStatus.unclassified, server_default="unclassified"
    )
    classification_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    industries = relationship("Industry", secondary=startup_industries)
