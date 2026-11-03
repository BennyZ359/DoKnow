"""Checked, atomic upgrades for new databases and the exact unversioned v0.1 schema."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, inspect, text
from sqlalchemy.engine import Connection, Engine

from .schema import baseline_metadata, current_metadata, editable_metadata, learning_metadata

BASELINE = "0001_baseline"
RECEIPTS = "0002_request_receipts"
LEARNING = "0003_learning_evidence"
CURRENT = "0004_editable_records"
VERSION_TABLE = "alembic_version"


class MigrationError(RuntimeError):
    """A database is not recognized or cannot be safely upgraded."""


def configuration() -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent).replace("%", "%%"))
    return config


def _shape(connection: Connection, metadata: MetaData) -> dict:
    """Compare portable SQL semantics, excluding generated constraint names."""
    tables = {}
    for name, table in metadata.tables.items():
        tables[name] = {
            "columns": {
                column.name: (
                    column.type.compile(dialect=connection.dialect).upper(),
                    column.nullable,
                    str(column.server_default.arg) if column.server_default is not None else None,
                ) for column in table.columns
            },
            "primary_key": tuple(column.name for column in table.primary_key.columns),
            "foreign_keys": sorted(
                (tuple(element.parent.name for element in constraint.elements),
                 tuple(element.target_fullname for element in constraint.elements),
                 constraint.ondelete, constraint.onupdate, constraint.deferrable,
                 constraint.initially, constraint.match)
                for constraint in table.foreign_key_constraints
            ),
            "indexes": sorted(
                (index.name, tuple(column.name for column in index.columns), bool(index.unique),
                 tuple(sorted((key, str(value)) for key, value in index.dialect_kwargs.items())))
                for index in table.indexes
            ),
        }
    return tables


def validate_schema(connection: Connection, expected: MetaData, *, versioned: bool) -> None:
    inspector = inspect(connection)
    names = set(inspector.get_table_names())
    allowed = set(expected.tables) | ({VERSION_TABLE} if versioned else set())
    if names != allowed or inspector.get_view_names():
        raise MigrationError("Database tables do not match a supported DoKnow schema; no migration was applied.")
    if versioned:
        columns = inspector.get_columns(VERSION_TABLE)
        primary_key = inspector.get_pk_constraint(VERSION_TABLE).get("constrained_columns")
        if (len(columns) != 1 or columns[0]["name"] != "version_num" or columns[0]["nullable"]
                or columns[0]["type"].compile(dialect=connection.dialect).upper() != "VARCHAR(32)"
                or primary_key != ["version_num"]):
            raise MigrationError("Invalid database revision table; no migration was applied.")
    if connection.dialect.name == "sqlite":
        if connection.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE type='trigger' LIMIT 1").first():
            raise MigrationError("Custom SQLite triggers require manual migration review.")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
            raise MigrationError("Database contains invalid foreign-key relationships; restore or repair before upgrading.")
        for name, table in expected.tables.items():
            # SQLAlchemy skips unsupported expression indexes when reflecting SQLite.
            names = {row[1] for row in connection.exec_driver_sql(f'PRAGMA index_list("{name}")') if row[3] == "c"}
            if names != {index.name for index in table.indexes}:
                raise MigrationError(f"Unrecognized SQLite indexes in {name}; no migration was applied.")
    for name in expected.tables:
        if inspector.get_unique_constraints(name) or inspector.get_check_constraints(name):
            raise MigrationError(f"Unrecognized constraints in {name}; no migration was applied.")
    actual = MetaData()
    actual.reflect(bind=connection, only=list(expected.tables))
    if _shape(connection, actual) != _shape(connection, expected):
        raise MigrationError("Database columns, keys or indexes differ from the recorded schema; no migration was applied.")


def metadata_for_revision(revision: str) -> MetaData:
    if revision == BASELINE:
        return baseline_metadata()
    if revision == RECEIPTS:
        return current_metadata()
    if revision == LEARNING:
        return learning_metadata()
    if revision == CURRENT:
        return editable_metadata()
    raise MigrationError("Database revision is unknown to this application; use the matching application version.")


def _upgrade(connection: Connection) -> str:
    config = configuration()
    config.attributes["connection"] = connection
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    names = set(inspect(connection).get_table_names())
    if VERSION_TABLE in names:
        revision_columns = inspect(connection).get_columns(VERSION_TABLE)
        if len(revision_columns) != 1 or revision_columns[0]["name"] != "version_num":
            raise MigrationError("Invalid database revision table; no migration was applied.")
        revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if len(revisions) != 1:
            raise MigrationError("Missing or ambiguous database revision; no migration was applied.")
        validate_schema(connection, metadata_for_revision(revisions[0]), versioned=True)
    elif names:
        validate_schema(connection, baseline_metadata(), versioned=False)
        command.stamp(config, BASELINE)
    elif inspect(connection).get_view_names():
        raise MigrationError("Unknown database views; no migration was applied.")
    command.upgrade(config, "head")
    validate_schema(connection, metadata_for_revision(head), versioned=True)
    return head


def initialize_database(engine: Engine) -> str:
    """Upgrade under one write lock and roll back all schema/version changes on failure."""
    if engine.dialect.name not in {"sqlite", "postgresql"}:
        raise MigrationError("Only SQLite and PostgreSQL migrations are supported.")
    with engine.connect() as connection:
        try:
            if engine.dialect.name == "sqlite":
                # Python's sqlite3 legacy transaction mode otherwise auto-commits DDL.
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                connection.begin()
                connection.execute(text("SELECT pg_advisory_xact_lock(2045379801)"))
            revision = _upgrade(connection)
            connection.commit()
            return revision
        except Exception:
            connection.rollback()
            raise
