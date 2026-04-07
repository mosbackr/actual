import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base

expert_industries = Table(
    "expert_industries",
    Base.metadata,
    Column("expert_id", UUID(as_uuid=True), ForeignKey("expert_profiles.id"), primary_key=True),
    Column("industry_id", UUID(as_uuid=True), ForeignKey("industries.id"), primary_key=True),
)

expert_skills = Table(
    "expert_skills",
    Base.metadata,
    Column("expert_id", UUID(as_uuid=True), ForeignKey("expert_profiles.id"), primary_key=True),
    Column("skill_id", UUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True),
)


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ExpertProfile(Base):
    __tablename__ = "expert_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)
    years_experience: Mapped[int] = mapped_column(Integer, nullable=False)
    application_status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), nullable=False, default=ApplicationStatus.pending
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    industries = relationship("Industry", secondary=expert_industries)
    skills = relationship("Skill", secondary=expert_skills)
