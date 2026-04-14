import enum
import uuid as _uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, JSON, UUID
from sqlalchemy.orm import relationship

from app.models.industry import Base


class MessageRole(enum.Enum):
    user = "user"
    assistant = "assistant"


class ReportFormat(enum.Enum):
    docx = "docx"
    xlsx = "xlsx"
    pdf = "pdf"
    pptx = "pptx"


class ReportGenStatus(enum.Enum):
    pending = "pending"
    generating = "generating"
    complete = "complete"
    failed = "failed"


messagerole_enum = ENUM("user", "assistant", name="messagerole", create_type=False)
reportformat_enum = ENUM("docx", "xlsx", "pdf", "pptx", name="reportformat", create_type=False)
reportgenstatus_enum = ENUM(
    "pending", "generating", "complete", "failed", name="reportgenstatus", create_type=False
)


class AnalystConversation(Base):
    __tablename__ = "analyst_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False, server_default="New Conversation")
    share_token = Column(String(64), unique=True, nullable=True)
    is_free_conversation = Column(Boolean, nullable=False, server_default="false")
    message_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship(
        "AnalystMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AnalystMessage.created_at",
    )
    reports = relationship(
        "AnalystReport",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    user = relationship("User")


class AnalystMessage(Base):
    __tablename__ = "analyst_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(messagerole_enum, nullable=False)
    content = Column(Text, nullable=False)
    charts = Column(JSON, nullable=True)
    citations = Column(JSON, nullable=True)
    context_startups = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("AnalystConversation", back_populates="messages")


class AnalystReport(Base):
    __tablename__ = "analyst_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    format = Column(reportformat_enum, nullable=False)
    status = Column(reportgenstatus_enum, nullable=False, server_default="pending")
    s3_key = Column(String(1000), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("AnalystConversation", back_populates="reports")
    user = relationship("User")
