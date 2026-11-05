"""Learning Goal module entities (whitepaper §12).

The goal is the entry point of the whole system: the user states what they
want to achieve, and every downstream artifact (knowledge system, learning
path, courses, tasks) is scoped to a goal.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class GoalStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class LearningGoal(Base, UUIDPKMixin, TimestampMixin):
    """A user-stated learning objective driving the entire pipeline."""

    __tablename__ = "learning_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_level: Mapped[str | None] = mapped_column(
        String(50)
    )  # e.g. beginner/intermediate/advanced
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[GoalStatus] = mapped_column(
        pg_enum(GoalStatus, "goal_status"), default=GoalStatus.DRAFT, server_default="DRAFT"
    )
    priority: Mapped[int] = mapped_column(default=3, server_default="3")
    # user-defined success criteria, e.g. "可以独立完成一个 Vue 3 项目"
    success_criteria: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    progress: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
