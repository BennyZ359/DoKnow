"""Assessment module entities (whitepaper §12).

Mastery is tracked per knowledge point and is distinct from task completion:
a task can be finished while mastery stays low. Assessments produce mastery
updates; reviews are scheduled reinforcement of decaying knowledge.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class AssessmentType(StrEnum):
    PRE_TEST = "PRE_TEST"
    EXERCISE = "EXERCISE"
    PROJECT = "PROJECT"
    QUIZ = "QUIZ"
    EXAM = "EXAM"
    EXPLAIN = "EXPLAIN"  # 讲 — assessed explanation


class MasteryState(StrEnum):
    COMPLETED = "COMPLETED"
    MASTERED = "MASTERED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    IN_PROGRESS = "IN_PROGRESS"
    NOT_STARTED = "NOT_STARTED"


class ReviewType(StrEnum):
    SPACED = "SPACED"
    WEAKNESS = "WEAKNESS"
    MANUAL = "MANUAL"


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    DUE = "DUE"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class Assessment(Base, UUIDPKMixin, TimestampMixin):
    """A measurement of mastery, produced by any assessment type."""

    __tablename__ = "assessments"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    assessment_type: Mapped[AssessmentType] = mapped_column(
        pg_enum(AssessmentType, "assessment_type"), default=AssessmentType.EXERCISE
    )
    score: Mapped[float | None] = mapped_column(Float)  # 0..1
    confidence: Mapped[float | None] = mapped_column(Float)  # 0..1
    result: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MasteryRecord(Base, UUIDPKMixin, TimestampMixin):
    """Latest mastery state for a knowledge point (one row per point)."""

    __tablename__ = "mastery_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    mastery_state: Mapped[MasteryState] = mapped_column(
        pg_enum(MasteryState, "mastery_state"),
        default=MasteryState.NOT_STARTED,
        server_default="NOT_STARTED",
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")  # 0..1
    confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    # evidence trail: assessment_ids that informed this state
    evidence: Mapped[list | None] = mapped_column(JSONB, default=list)
    last_assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class ReviewTask(Base, UUIDPKMixin, TimestampMixin):
    """A scheduled reinforcement of a knowledge point (spaced / weakness)."""

    __tablename__ = "review_tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    review_type: Mapped[ReviewType] = mapped_column(
        pg_enum(ReviewType, "review_type"), default=ReviewType.SPACED
    )
    status: Mapped[ReviewStatus] = mapped_column(
        pg_enum(ReviewStatus, "review_status"),
        default=ReviewStatus.PENDING,
        server_default="PENDING",
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_days: Mapped[int | None] = mapped_column(Integer)
    # e.g. Ebbinghaus interval sequence
    schedule: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
