import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.industry import Base


class FeedbackSession(Base):
    __tablename__ = "feedback_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, server_default="active")
    category = Column(String(50))
    severity = Column(String(20))
    area = Column(String(100))
    summary = Column(Text)
    recommendations = Column(JSONB)
    transcript = Column(JSONB)
    page_url = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
