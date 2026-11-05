"""Practice module entities (whitepaper §12).

Learning tasks are the daily units the orchestrator assigns; exercises and
practice projects are the "练" and "用" side of the 学/练/用/讲/温 loop.
Attempts are append-only so assessment can reason over progress.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class TaskType(StrEnum):
    STUDY = "STUDY"  # 学
    PRACTICE = "PRACTICE"  # 练
    APPLY = "APPLY"  # 用
    EXPLAIN = "EXPLAIN"  # 讲
    REVIEW = "REVIEW"  # 温
    PROJECT = "PROJECT"


class TaskStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    EXPIRED = "EXPIRED"


class QuestionType(StrEnum):
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"
    CODE = "CODE"
    PROJECT = "PROJECT"


class LearningTask(Base, UUIDPKMixin, TimestampMixin):
    """A daily unit of work assigned by the orchestrator for one knowledge point."""

    __tablename__ = "learning_tasks"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"), index=True
    )
    task_type: Mapped[TaskType] = mapped_column(
        pg_enum(TaskType, "task_type"), default=TaskType.STUDY
    )
    status: Mapped[TaskStatus] = mapped_column(
        pg_enum(TaskStatus, "task_status"),
        default=TaskStatus.NOT_STARTED,
        server_default="NOT_STARTED",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    est_minutes: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class Exercise(Base, UUIDPKMixin, TimestampMixin):
    """A question generated for practice on a knowledge point."""

    __tablename__ = "exercises"

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_tasks.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    question_type: Mapped[QuestionType] = mapped_column(
        pg_enum(QuestionType, "question_type"), default=QuestionType.SINGLE_CHOICE
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # options / expected answer / grading rubric in flexible JSON
    content: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    difficulty: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ExerciseAttempt(Base, UUIDPKMixin, TimestampMixin):
    """One submission for an exercise (append-only; assessment reads these)."""

    __tablename__ = "exercise_attempts"

    exercise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_tasks.id", ondelete="SET NULL"), index=True
    )
    user_answer: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    # 0..1 progress toward mastery for this point after this attempt
    mastery_estimate: Mapped[float | None] = mapped_column(Float)


class PracticeProject(Base, UUIDPKMixin, TimestampMixin):
    """A hands-on "用" task: build something that exercises multiple points."""

    __tablename__ = "practice_projects"

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_tasks.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # the knowledge points this project exercises
    knowledge_point_ids: Mapped[list | None] = mapped_column(JSONB, default=list)
    acceptance_criteria: Mapped[list | None] = mapped_column(JSONB, default=list)
    rubric: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", server_default="PENDING")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
