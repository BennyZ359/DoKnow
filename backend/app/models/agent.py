"""Agent runtime entities (whitepaper §12, §13.2).

Agents are the AI side of the system. They never touch the DB directly —
they operate through business services and record their runs/checkpoints here
so a run can be resumed after a crash (LangGraph checkpoint persistence).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum


class AgentType(StrEnum):
    LEARNING_MANAGER = "LEARNING_MANAGER"  # 长驻编排：观察→诊断→决策→行动→评估
    COURSE_AGENT = "COURSE_AGENT"  # 临时运行：为一次课程生成/教学服务
    KNOWLEDGE_BUILDER = "KNOWLEDGE_BUILDER"
    CURRICULUM_PLANNER = "CURRICULUM_PLANNER"
    TEACHING_ENGINE = "TEACHING_ENGINE"
    EXERCISE_GENERATOR = "EXERCISE_GENERATOR"
    ASSESSMENT_ENGINE = "ASSESSMENT_ENGINE"
    REVIEW_ENGINE = "REVIEW_ENGINE"
    CONTENT_QUALITY_CHECKER = "CONTENT_QUALITY_CHECKER"
    MEMORY_MANAGER = "MEMORY_MANAGER"


class AgentRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


class AgentDefinition(Base, UUIDPKMixin, TimestampMixin):
    """Declarative registry of an agent type: its graph and capabilities."""

    __tablename__ = "agent_definitions"

    agent_type: Mapped[AgentType] = mapped_column(
        pg_enum(AgentType, "agent_type"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    graph_name: Mapped[str | None] = mapped_column(String(120))
    # model / temperature / tool permissions (allowlist)
    config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    max_retries: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="300")


class AgentRun(Base, UUIDPKMixin, TimestampMixin):
    """One execution of an agent, for a subject (goal/course/task)."""

    __tablename__ = "agent_runs"

    agent_type: Mapped[AgentType] = mapped_column(
        pg_enum(AgentType, "agent_type"), index=True, nullable=False
    )
    # subject of the run: LearningGoal / Course / LearningTask / ...
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        pg_enum(AgentRunStatus, "agent_run_status"),
        default=AgentRunStatus.PENDING,
        server_default="PENDING",
    )
    input_payload: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    error: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    # heartbeat of a long-running manager
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class AgentCheckpoint(Base, UUIDPKMixin, TimestampMixin):
    """A persisted checkpoint of a run (LangGraph checkpoint saver mirror)."""

    __tablename__ = "agent_checkpoints"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    checkpoint_id: Mapped[str] = mapped_column(String(120), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    checkpoint_ns: Mapped[str] = mapped_column(String(255), default="", server_default="")
    checkpoint: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    # DB column keeps LangGraph's "metadata" name; the attribute is renamed
    # because Declarative reserves "metadata" for the class MetaData instance.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(120))
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
