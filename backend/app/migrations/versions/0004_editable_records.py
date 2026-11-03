"""Version basic edits and retain the original knowledge before its first edit."""

from alembic import op
from sqlalchemy import Column, DateTime, Integer, JSON, text

revision = "0004_editable_records"
down_revision = "0003_learning_evidence"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("goals", "knowledge_entries"):
        op.add_column(table, Column("version", Integer, nullable=False, server_default=text("1")))
        op.add_column(table, Column("updated_at", DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {table} SET updated_at = created_at")
    op.add_column("knowledge_entries", Column("tags", JSON, nullable=True))
    op.add_column("knowledge_entries", Column("original", JSON, nullable=True))


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled. Restore a verified backup to a new database.")
