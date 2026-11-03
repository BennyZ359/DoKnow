"""Frozen schemas: revisions must not import tomorrow's application models."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, MetaData, String, Table, Text, text


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


def editable_metadata() -> MetaData:
    metadata = learning_metadata()
    for name in ("goals", "knowledge_entries"):
        metadata.tables[name].append_column(Column("version", Integer, nullable=False, server_default=text("1")))
        metadata.tables[name].append_column(Column("updated_at", DateTime(timezone=True), nullable=True))
    metadata.tables["knowledge_entries"].append_column(Column("tags", JSON, nullable=True))
    metadata.tables["knowledge_entries"].append_column(Column("original", JSON, nullable=True))
    return metadata


def course_metadata() -> MetaData:
    metadata = editable_metadata()
    metadata.tables["goals"].append_column(Column("course_version", Integer, nullable=False, server_default=text("1")))
    metadata.tables["units"].append_column(Column("archived", Integer, nullable=False, server_default=text("0")))
    Table(
        "course_changes", metadata,
        Column("id", String(36), primary_key=True),
        Column("goal_id", String(36), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("kind", String(20), nullable=False),
        Column("base_version", Integer, nullable=False),
        Column("goal_version", Integer, nullable=False),
        Column("snapshot", JSON, nullable=False),
        Column("proposal", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("applied_at", DateTime(timezone=True), nullable=True),
    )
    return metadata


def roadmap_metadata() -> MetaData:
    metadata = course_metadata()
    Table(
        "roadmaps", metadata,
        Column("id", String(36), primary_key=True),
        Column("topic", String(200), nullable=False),
        Column("plan", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    return metadata


def concept_graph_metadata() -> MetaData:
    metadata = roadmap_metadata()
    Table(
        "concept_graphs", metadata,
        Column("id", String(36), primary_key=True),
        Column("topic", String(200), nullable=False),
        Column("summary", Text, nullable=False),
        Column("focus_id", String(36), nullable=False),
        Column("provenance", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Table(
        "knowledge_entities", metadata,
        Column("id", String(36), primary_key=True),
        Column("graph_id", String(36), ForeignKey("concept_graphs.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("key", String(60), nullable=False),
        Column("name", String(70), nullable=False),
        Column("kind", String(20), nullable=False, index=True),
        Column("description", Text, nullable=False),
        Column("aliases", JSON, nullable=False),
        Column("properties", JSON, nullable=False),
        Column("provenance", JSON, nullable=False),
    )
    Table(
        "knowledge_relations", metadata,
        Column("id", String(36), primary_key=True),
        Column("graph_id", String(36), ForeignKey("concept_graphs.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("source_id", String(36), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("target_id", String(36), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("kind", String(24), nullable=False, index=True),
        Column("explanation", Text, nullable=False),
        Column("provenance", JSON, nullable=False),
    )
    return metadata
