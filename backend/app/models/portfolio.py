import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class PortfolioCompany(Base):
    __tablename__ = "portfolio_companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investors.id", ondelete="CASCADE"),
        nullable=False,
    )
    startup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("startups.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    company_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    investment_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    round_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    check_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_lead: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    board_seat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    exit_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exit_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("investor_id", "company_name", name="uq_portfolio_investor_company"),
    )
