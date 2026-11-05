"""initial schema: pgvector extension + all domain tables

Baseline migration. Creates the full whitepaper domain schema (27 tables,
24 named enum types, see app/models/) directly from the SQLAlchemy metadata.

Design note: rather than hand-copying every column into op.create_table calls
(guaranteed to drift), the baseline builds the schema from the same metadata
the app uses — the single source of truth. Future schema changes MUST use
``alembic revision --autogenerate``, which diffs cleanly against this
baseline because the resulting schema is exactly Base.metadata.

Requires the pgvector extension in the database image (pgvector/pgvector:pg16
in docker-compose ships it; the connected user owns the database).

Revision ID: 0001
Revises:
Create Date: 2026-11-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.database import Base

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector must exist before any VECTOR column is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Creates enum types, tables, FKs, indexes in dependency order.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("DROP EXTENSION IF EXISTS vector")
