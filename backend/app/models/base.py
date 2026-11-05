"""Shared SQLAlchemy model primitives.

All domain models derive from :class:`Base` and mix in the UUID primary key
and timestamp columns so identity/audit handling is uniform across the schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UUIDPKMixin:
    """UUID primary key (application-generated, not DB sequence)."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """created_at / updated_at audit columns (timezone-aware, server-side)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Build a named PostgreSQL enum type from a ``str`` enum.

    ``values_callable`` stores the enum *values* (not member names) in the DB,
    so e.g. ``MasteryState.MASTERED`` is persisted as ``"MASTERED"``.
    The ``name`` argument fixes the PostgreSQL type name, which is required
    for Alembic autogenerate to track the type identity across migrations.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [v.value for v in e])


__all__ = ["Base", "UUIDPKMixin", "TimestampMixin", "pg_enum"]
