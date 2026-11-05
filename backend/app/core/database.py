"""SQLAlchemy engine, session factory, and declarative base.

Design decision: a *synchronous* SQLAlchemy 2.0 engine with the psycopg driver.
The domain is transaction-heavy and business-service owned; the agent runtime
runs in a threadpool so the sync engine keeps the code path simple and avoids
async-session pitfalls with LangGraph checkpoints. pgvector is registered via
the ``pgvector.sqlalchemy`` extension.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def _json_default(obj: object) -> object:
    """Make JSONB columns tolerant of domain types that leak into payloads.

    Agent-run outputs and memory payloads are stored as JSONB, and service
    returns sometimes carry ``uuid.UUID`` / ``datetime`` objects. Without this
    default the driver's ``json.dumps`` raises "Object of type UUID is not JSON
    serializable" and the whole agent run fails after doing all the work.
    """
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    echo=settings.debug,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False, default=_json_default),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. For tests/dev only; production uses Alembic."""
    # Import models so they register with Base before create_all.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
