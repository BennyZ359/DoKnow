"""Preserve assessment provenance and practice progress without inventing history."""

from alembic import op
from sqlalchemy import Column, JSON

revision = "0003_learning_evidence"
down_revision = "0002_request_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("units", Column("practice_state", JSON, nullable=True))
    op.add_column("learning_sessions", Column("assessment", JSON, nullable=True))


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled. Restore a verified backup to a new database.")
