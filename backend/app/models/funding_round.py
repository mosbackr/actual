import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class StartupFundingRound(Base):
    __tablename__ = "startup_funding_rounds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    round_name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lead_investor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    other_investors: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pre_money_valuation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    post_money_valuation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_source: Mapped[str] = mapped_column(String(20), nullable=False, default="perplexity", server_default="perplexity")
