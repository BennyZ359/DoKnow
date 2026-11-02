"""DoKnow data maintenance. Backup/restore only ever create a new destination."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from .database import make_database
from .migrations import (
    BASELINE, VERSION_TABLE, MigrationError, initialize_database, metadata_for_revision, validate_schema,
)


class DataError(RuntimeError):
    """A safe, actionable maintenance error without secrets or connection strings."""


def sqlite_path(database_url: str) -> Path:
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise DataError("Invalid database URL.") from exc
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:" or url.query:
        raise DataError("Backup/restore requires a file-backed SQLite URL without query parameters.")
    return Path(url.database).resolve()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)


def inspect_backup(path: Path) -> dict:
    """Validate the exact snapshot that will be published, without upgrading it."""
    path = path.resolve(strict=True)
    if not path.is_file():
        raise DataError("Source must be an existing SQLite database file.")
    try:
        with closing(_connect_readonly(path)) as db:
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise DataError("SQLite integrity check failed.")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise DataError("SQLite foreign-key check failed.")
        engine = create_engine("sqlite://", creator=lambda: _connect_readonly(path))
        try:
            with engine.connect() as connection:
                versioned = VERSION_TABLE in inspect(connection).get_table_names()
                revision = BASELINE
                if versioned:
                    revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
                    if len(revisions) != 1:
                        raise DataError("Backup has a missing or ambiguous revision.")
                    revision = revisions[0]
                metadata = metadata_for_revision(revision)
                validate_schema(connection, metadata, versioned=versioned)
                counts = {name: connection.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one()
                          for name in metadata.tables}
                return {"revision": revision if versioned else "unversioned-v0.1", "rows": counts}
        finally:
            engine.dispose()
    except (sqlite3.Error, SQLAlchemyError, MigrationError) as exc:
        raise DataError("Source is corrupt, unrecognized, or requires a different DoKnow version.") from exc


def copy_database(source: Path, destination: Path, *, timeout: float = 30) -> dict:
    """The SQLite backup API includes committed WAL data; exclusive create prevents overwrites."""
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination:
        raise DataError("Source and destination must differ.")
    if not destination.parent.is_dir():
        raise DataError("Destination directory must already exist.")
    # Even a missing main file can have a live WAL left by another process.
    if any(Path(str(destination) + suffix).exists() for suffix in ("", "-wal", "-shm", "-journal")):
        raise DataError("Destination or SQLite sidecars already exist. Choose a new file; stop the backend before switching databases.")
    created = False
    succeeded = False
    try:
        # xb/O_EXCL makes racing writers fail instead of replacing an existing database.
        with destination.open("xb"):
            created = True
        started = time.monotonic()

        def progress(_status: int, _remaining: int, _total: int) -> None:
            if time.monotonic() - started > timeout:
                raise DataError("Backup timed out because the database remained busy; retry later.")

        with closing(_connect_readonly(source)) as incoming, closing(sqlite3.connect(destination)) as outgoing:
            incoming.backup(outgoing, pages=256, progress=progress, sleep=0.05)
            # Publish a standalone file, not a database dependent on sidecars.
            outgoing.execute("PRAGMA journal_mode=DELETE")
        details = inspect_backup(destination)
        with destination.open("r+b") as stream:
            os.fsync(stream.fileno())
        succeeded = True
        return {"path": str(destination), **details}
    except FileExistsError as exc:
        raise DataError("Destination already exists; choose a new file.") from exc
    except sqlite3.Error as exc:
        raise DataError("Could not read or copy the SQLite database.") from exc
    finally:
        if created and not succeeded:
            # Only delete this call's new output, never the user's source or existing target.
            destination.unlink(missing_ok=True)


def backup_database(database_url: str, destination: Path) -> dict:
    return copy_database(sqlite_path(database_url), destination)


def restore_database(source: Path, database_url: str) -> dict:
    destination = sqlite_path(database_url)
    # Check the source first, then re-check the copied snapshot to cover concurrent changes.
    inspect_backup(source)
    return copy_database(source, destination)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser("migrate", help="Validate and upgrade the configured database")
    migrate.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///./data/doknow.db"))
    backup = commands.add_parser("backup", help="Create a new, verified SQLite backup, including committed WAL data")
    backup.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///./data/doknow.db"))
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore", help="Restore to a NEW database path; existing files are never replaced")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--database-url", required=True, help="Explicit new SQLite database URL")
    verify = commands.add_parser("verify", help="Read-only integrity, schema and row-count inspection")
    verify.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "migrate":
            engine, _ = make_database(args.database_url)
            try:
                result = {"revision": initialize_database(engine)}
            finally:
                engine.dispose()
        elif args.command == "backup":
            result = backup_database(args.database_url, args.output)
        elif args.command == "restore":
            result = restore_database(args.input, args.database_url)
        else:
            result = inspect_backup(args.input)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (DataError, MigrationError, OSError) as exc:
        print(f"Data operation failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        # SQLAlchemy exceptions can contain database passwords and learner values.
        print("Data operation failed. Check database access and supported schema; no successful backup or upgrade was reported.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
