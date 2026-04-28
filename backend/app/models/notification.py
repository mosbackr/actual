import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.models.industry import Base


class NotificationType(enum.Enum):
    analysis_complete = "analysis_complete"
    report_ready = "report_ready"
    memo_complete = "memo_complete"
    dataroom_submitted = "dataroom_submitted"
    dataroom_complete = "dataroom_complete"


notificationtype_enum = ENUM(
    "analysis_complete", "report_ready", "memo_complete",
    "dataroom_submitted", "dataroom_complete",
    name="notificationtype", create_type=False,
)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(notificationtype_enum, nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(String(500), nullable=False)
    link = Column(String(500), nullable=False)
    read = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
