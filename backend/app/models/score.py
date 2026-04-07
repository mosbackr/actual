import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class ScoreType(str, enum.Enum):
    ai = "ai"
    expert_aggregate = "expert_aggregate"
    user_aggregate = "user_aggregate"


class StartupScoreHistory(Base):
    __tablename__ = "startup_scores_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("startups.id"), nullable=False)
    score_type: Mapped[ScoreType] = mapped_column(Enum(ScoreType), nullable=False)
    score_value: Mapped[float] = mapped_column(Float, nullable=False)
    dimensions_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
