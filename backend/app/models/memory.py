"""Memory module entities (whitepaper §12).

Three-layer memory: Global Memory (user profile / learner memory), Course
Memory (per-course context), and Learning Events (the stream of observations
the proactive intervention loop reasons over). Every memory entry records a
source, a confidence, and a scope so the AI never silently overwrites facts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class EventSource(StrEnum):
    USER_INPUT = "USER_INPUT"  # 用户明确陈述的事实
    SYSTEM_FACT = "SYSTEM_FACT"  # 系统确定性数据（如考试成绩）
    AI_ASSESSMENT = "AI_ASSESSMENT"  # AI 基于证据的评估
    AI_GUESS = "AI_GUESS"  # AI 推断/猜测，低置信度


class MemoryType(StrEnum):
    PREFERENCE = "PREFERENCE"
    KNOWLEDGE_STATE = "KNOWLEDGE_STATE"
    LEARNING_STYLE = "LEARNING_STYLE"
    GOAL_CONTEXT = "GOAL_CONTEXT"
    BEHAVIOR = "BEHAVIOR"
    EVENT = "EVENT"


class LearningEvent(Base, UUIDPKMixin, TimestampMixin):
    """An append-only observation feeding the Observe step of the loop.

    Events are never edited; the intervention loop reads them to diagnose.
    """

    __tablename__ = "learning_events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    # LearningTask / Assessment / ReviewTask / CourseVersion
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column()
    causation_id: Mapped[uuid.UUID | None] = mapped_column()


class LearnerMemory(Base, UUIDPKMixin, TimestampMixin):
    """Global Memory: durable facts about the learner across goals."""

    __tablename__ = "learner_memories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        pg_enum(MemoryType, "memory_type"), default=MemoryType.PREFERENCE
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    source: Mapped[EventSource] = mapped_column(
        pg_enum(EventSource, "event_source"), default=EventSource.AI_GUESS
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    scope: Mapped[str] = mapped_column(String(64), default="GLOBAL", server_default="GLOBAL")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class CourseMemory(Base, UUIDPKMixin, TimestampMixin):
    """Per-course memory: context the course agent needs while teaching."""

    __tablename__ = "course_memories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        pg_enum(MemoryType, "memory_type"), default=MemoryType.GOAL_CONTEXT
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    source: Mapped[EventSource] = mapped_column(
        pg_enum(EventSource, "event_source"), default=EventSource.AI_ASSESSMENT
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
