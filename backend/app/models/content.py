"""Content quality module entities (whitepaper §12, §10.2).

Document parsing provenance (Docling / MinerU) and content quality reports.
Content quality is a first-class gate: courses the checker flags do not get
published to learners until the issue is resolved or accepted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class SourceType(StrEnum):
    PDF = "PDF"
    DOCX = "DOCX"
    PPTX = "PPTX"
    MARKDOWN = "MARKDOWN"
    HTML = "HTML"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"
    URL = "URL"


class SourceStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class QualityStage(StrEnum):
    GENERATION = "GENERATION"
    PARSE = "PARSE"
    PREVIEW = "PREVIEW"
    PUBLICATION = "PUBLICATION"


class QualityStatus(StrEnum):
    PASSED = "PASSED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    PENDING = "PENDING"


class Reviewer(StrEnum):
    AI_CONTENT_CHECKER = "AI_CONTENT_CHECKER"
    HUMAN_REVIEWER = "HUMAN_REVIEWER"
    SYSTEM_RULE = "SYSTEM_RULE"


class ContentSource(Base, UUIDPKMixin, TimestampMixin):
    """An uploaded/imported source document that feeds course generation."""

    __tablename__ = "content_sources"

    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        pg_enum(SourceType, "source_type"), default=SourceType.PDF
    )
    status: Mapped[SourceStatus] = mapped_column(
        pg_enum(SourceStatus, "source_status"),
        default=SourceStatus.UPLOADED,
        server_default="UPLOADED",
    )
    # original filename / object-store key / external URL
    filename: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    source_url: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    # parser backend used (docling / mineru) and its settings
    parser_backend: Mapped[str] = mapped_column(
        String(32), default="docling", server_default="docling"
    )
    # parser output: structured blocks, extracted text, figures, tables
    parsed_content: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    parse_error: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    # extracted knowledge points (candidates)
    extracted_knowledge: Mapped[list | None] = mapped_column(JSONB, default=list)
    # embedding of the parsed text for semantic retrieval
    embedding: Mapped[list | None] = mapped_column(JSONB, default=list)
    language: Mapped[str | None] = mapped_column(String(16), default="zh")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class ContentQualityReport(Base, UUIDPKMixin, TimestampMixin):
    """A check result on some piece of generated/parsed content."""

    __tablename__ = "content_quality_reports"

    # CourseVersion / Lesson / Course / ContentSource
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    stage: Mapped[QualityStage] = mapped_column(
        pg_enum(QualityStage, "quality_stage"), default=QualityStage.GENERATION
    )
    status: Mapped[QualityStatus] = mapped_column(
        pg_enum(QualityStatus, "quality_status"),
        default=QualityStatus.PENDING,
        server_default="PENDING",
    )
    reviewer: Mapped[Reviewer] = mapped_column(
        pg_enum(Reviewer, "reviewer"), default=Reviewer.AI_CONTENT_CHECKER
    )
    # category: accuracy / completeness / coherence / formatting / citation / safety
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM", server_default="MEDIUM")
    score: Mapped[float | None] = mapped_column(Float)  # 0..1
    findings: Mapped[list | None] = mapped_column(JSONB, default=list)
    recommendation: Mapped[str | None] = mapped_column(Text)
    # resolved by regenerating content or accepted as-is
    resolution: Mapped[str | None] = mapped_column(String(32))
    resolved_by: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
