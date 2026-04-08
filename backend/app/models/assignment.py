import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class AssignmentStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class StartupAssignment(Base):
    __tablename__ = "startup_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("startups.id"), nullable=False)
    expert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("expert_profiles.id"), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus), nullable=False, default=AssignmentStatus.pending
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    startup = relationship("Startup")
    expert = relationship("ExpertProfile")
    assigner = relationship("User", foreign_keys=[assigned_by])
