"""Frozen schemas: revisions must not import tomorrow's application models."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, MetaData, String, Table, Text


def baseline_metadata() -> MetaData:
    metadata = MetaData()
    Table(
        "goals", metadata,
        Column("id", String(36), primary_key=True),
        Column("title", String(200), nullable=False),
        Column("motivation", Text, nullable=False),
        Column("level", String(20), nullable=False),
        Column("daily_minutes", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Table(
        "units", metadata,
        Column("id", String(36), primary_key=True),
        Column("goal_id", String(36), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("title", String(200), nullable=False),
        Column("objective", Text, nullable=False),
        Column("position", Integer, nullable=False),
        Column("stage", String(20), nullable=False, index=True),
        Column("mastery", Integer, nullable=False),
        Column("material", JSON, nullable=False),
        Column("review_due_at", DateTime(timezone=True), nullable=True, index=True),
        Column("review_count", Integer, nullable=False),
        Column("review_streak", Integer, nullable=False),
        Column("version", Integer, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Column("completed_at", DateTime(timezone=True), nullable=True),
    )
    Table(
        "learning_sessions", metadata,
        Column("id", String(36), primary_key=True),
        Column("unit_id", String(36), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("kind", String(20), nullable=False),
        Column("content", Text, nullable=False),
        Column("feedback", Text, nullable=False),
        Column("score", Integer, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    )
    Table(
        "knowledge_entries", metadata,
        Column("id", String(36), primary_key=True),
        Column("title", String(200), nullable=False),
        Column("content", Text, nullable=False),
        Column("source", String(255), nullable=False),
        Column("unit_id", String(36), ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    return metadata


def current_metadata() -> MetaData:
    """Frozen revision 0002; keep this definition stable for existing databases."""
    metadata = baseline_metadata()
    Table(
        "request_receipts", metadata,
        Column("key", String(128), primary_key=True),
        Column("fingerprint", String(64), nullable=False),
        Column("owner_token", String(36), nullable=False),
        Column("status", String(16), nullable=False),
        Column("lease_until", DateTime(timezone=True), nullable=False),
        Column("response_status", Integer, nullable=True),
        Column("response_body", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("completed_at", DateTime(timezone=True), nullable=True),
        Column("resource_scope", String(80), nullable=True),
    )
    return metadata


def learning_metadata() -> MetaData:
    metadata = current_metadata()
    metadata.tables["units"].append_column(Column("practice_state", JSON, nullable=True))
    metadata.tables["learning_sessions"].append_column(Column("assessment", JSON, nullable=True))
    return metadata
