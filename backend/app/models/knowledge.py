"""Knowledge module entities (whitepaper §12).

The knowledge system is the graph the AI builds from the goal: domains,
knowledge points (each with its own mastery state, independent of any course)
and typed relations between points (prerequisite / related / extension /
application). Semantic embeddings power recall and retrieval.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class KnowledgeType(StrEnum):
    CONCEPT = "CONCEPT"
    FACT = "FACT"
    PROCEDURE = "PROCEDURE"
    PRINCIPLE = "PRINCIPLE"
    SKILL = "SKILL"
    METHOD = "METHOD"


class Difficulty(StrEnum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class RelationType(StrEnum):
    PREREQUISITE = "PREREQUISITE"
    RELATED = "RELATED"
    EXTENSION = "EXTENSION"
    APPLICATION = "APPLICATION"


class KnowledgeDomain(Base, UUIDPKMixin, TimestampMixin):
    """Top-level subject area, e.g. "前端开发" or "机器学习基础"."""

    __tablename__ = "knowledge_domains"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class KnowledgePoint(Base, UUIDPKMixin, TimestampMixin):
    """A single learnable concept/skill — the unit of mastery tracking.

    ``knowledge_type`` drives which learning method (学/练/用/讲/温) the
    curriculum picks for it. Mastery is owned here, not on courses, so it can
    be reused across courses and goals.
    """

    __tablename__ = "knowledge_points"

    domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64))  # human-readable id, e.g. KP-VUE-001
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    knowledge_type: Mapped[KnowledgeType] = mapped_column(
        pg_enum(KnowledgeType, "knowledge_type"), default=KnowledgeType.CONCEPT
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        pg_enum(Difficulty, "difficulty"), default=Difficulty.BEGINNER
    )
    # 学 / 练 / 用 / 讲 / 温 — which methods fit this knowledge type
    recommended_methods: Mapped[list | None] = mapped_column(ARRAY(String(20)), default=list)
    tags: Mapped[list | None] = mapped_column(ARRAY(String(64)), default=list)
    est_minutes: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list | None] = mapped_column(Vector(), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    __table_args__ = (UniqueConstraint("domain_id", "code", name="uq_kp_domain_code"),)


class KnowledgeRelation(Base, UUIDPKMixin, TimestampMixin):
    """Typed edge between two knowledge points."""

    __tablename__ = "knowledge_relations"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[RelationType] = mapped_column(
        pg_enum(RelationType, "relation_type"), default=RelationType.RELATED
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    # e.g. "学习 Vue 3 前应先掌握 JavaScript 基础"
    rationale: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
