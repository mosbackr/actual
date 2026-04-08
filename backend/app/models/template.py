import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class DueDiligenceTemplate(Base):
    __tablename__ = "due_diligence_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dimensions = relationship("TemplateDimension", back_populates="template", cascade="all, delete-orphan")


class TemplateDimension(Base):
    __tablename__ = "template_dimensions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("due_diligence_templates.id", ondelete="CASCADE"), nullable=False
    )
    dimension_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template = relationship("DueDiligenceTemplate", back_populates="dimensions")
