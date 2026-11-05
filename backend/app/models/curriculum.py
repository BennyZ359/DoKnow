"""Curriculum module entities (whitepaper §12).

The learning path is an ordered graph over knowledge points. From it the AI
generates courses (versioned) and lessons. Courses reference knowledge points
rather than owning them, which is what allows mastery to persist across
courses and unlocks to remain soft.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class PathStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class Sequence(StrEnum):
    FIXED = "FIXED"
    FLEXIBLE = "FLEXIBLE"


class CourseStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"
    RETIRED = "RETIRED"


class ContentFormat(StrEnum):
    MARKDOWN = "MARKDOWN"
    HTML = "HTML"
    VIDEO = "VIDEO"
    SLIDES = "SLIDES"
    PDF = "PDF"
    QUIZ = "QUIZ"
    PROJECT = "PROJECT"
    TUTORIAL = "TUTORIAL"


class LearningPath(Base, UUIDPKMixin, TimestampMixin):
    """The ordered roadmap the curriculum planner produces for a goal."""

    __tablename__ = "learning_paths"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PathStatus] = mapped_column(
        pg_enum(PathStatus, "path_status"), default=PathStatus.DRAFT, server_default="DRAFT"
    )
    total_est_minutes: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class LearningPathNode(Base, UUIDPKMixin, TimestampMixin):
    """One step in a learning path, tied to a knowledge point (not a course)."""

    __tablename__ = "learning_path_nodes"

    path_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[Sequence] = mapped_column(
        pg_enum(Sequence, "sequence"), default=Sequence.FIXED
    )
    # optional parent for tree-shaped paths
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_path_nodes.id", ondelete="SET NULL")
    )
    est_minutes: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    __table_args__ = (UniqueConstraint("path_id", "knowledge_point_id", name="uq_path_node_kp"),)


class Course(Base, UUIDPKMixin, TimestampMixin):
    """A course generated to teach a run of knowledge points."""

    __tablename__ = "courses"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    path_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CourseStatus] = mapped_column(
        pg_enum(CourseStatus, "course_status"), default=CourseStatus.DRAFT, server_default="DRAFT"
    )
    # active_version_id points at the published CourseVersion
    active_version_id: Mapped[uuid.UUID | None] = mapped_column()
    total_est_minutes: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CourseVersion(Base, UUIDPKMixin, TimestampMixin):
    """An immutable snapshot of a course's content (regenerable versions)."""

    __tablename__ = "course_versions"

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(String(255))
    # list of knowledge_point ids this version teaches
    knowledge_point_ids: Mapped[list | None] = mapped_column(JSONB, default=list)
    content: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (UniqueConstraint("course_id", "version_number", name="uq_course_version"),)


class Lesson(Base, UUIDPKMixin, TimestampMixin):
    """A unit of teaching within a course version."""

    __tablename__ = "lessons"

    course_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_versions.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    format: Mapped[ContentFormat] = mapped_column(
        pg_enum(ContentFormat, "content_format"), default=ContentFormat.MARKDOWN
    )
    # lesson body — markdown/html per ``format``
    body: Mapped[str | None] = mapped_column(Text)
    # knowledge point this lesson teaches
    knowledge_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"), index=True
    )
    est_minutes: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
