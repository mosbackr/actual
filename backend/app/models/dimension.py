import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class StartupDimension(Base):
    __tablename__ = "startup_dimensions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("startups.id"), nullable=False)
    dimension_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
