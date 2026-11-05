import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(16), default="strict")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    # Soft per-turn guidance [{topic, objective, difficulty}, ...]; NULL = legacy.
    question_plan: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionTurn(Base):
    __tablename__ = "session_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer)
    question_area: Mapped[str] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evaluation_coverage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evaluation_strengths: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    evaluation_gaps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    evaluation_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistance_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    assistance_events: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    assisted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
