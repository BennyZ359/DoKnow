"""Portable database setup with SQLite foreign-key enforcement."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_database(database_url: str):
    url = make_url(database_url)
    sqlite = url.get_backend_name() == "sqlite"
    if sqlite and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    extra = {"poolclass": StaticPool} if sqlite and url.database in (None, "", ":memory:") else {}
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 20} if sqlite else {},
        pool_pre_ping=True,
        **extra,
    )
    if sqlite:
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    return engine, sessionmaker(bind=engine, expire_on_commit=False)
