import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class MemoStatus(enum.Enum):
    pending = "pending"
    researching = "researching"
    generating = "generating"
    formatting = "formatting"
    complete = "complete"
    failed = "failed"


memostatus_enum = ENUM(
    "pending", "researching", "generating", "formatting", "complete", "failed",
    name="memostatus", create_type=False,
)


class InvestmentMemo(Base):
    __tablename__ = "investment_memos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pitch_analyses.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    status = mapped_column(memostatus_enum, nullable=False, default="pending")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    s3_key_pdf: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    s3_key_docx: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis = relationship("PitchAnalysis", back_populates="memo")
