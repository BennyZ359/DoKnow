"""Upgrade genuine v0.1 evidence, reject unknown schemas, and roll back failed DDL."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import inspect, select, text

from app.database import make_database
from app.migrations import CURRENT, MigrationError, initialize_database
from app.models import KnowledgeEntry, Unit


LEGACY_TABLES = ("goals", "units", "learning_sessions", "knowledge_entries")


@pytest.fixture
def legacy(tmp_path):
    path = tmp_path / "existing.db"
    goal_id = "00000000-0000-4000-8000-000000000001"
    unit_id = "00000000-0000-4000-8000-000000000002"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript((Path(__file__).parent / "fixtures/v0_1_schema.sql").read_text(encoding="utf-8"))
        connection.execute("INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?)",
                           (goal_id, "已有学习目标", "保留真实沉淀", "intermediate", 45, "2026-10-20 08:15:30.123456"))
        material = {"lesson": {"explanation": "中文材料", "example": "return x * 2"},
                    "practice": {"options": ["打印", "返回"], "correct_index": 1},
                    "project": {"criteria": ["输入", "输出", "边界"]}}
        connection.execute("INSERT INTO units VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (unit_id, goal_id, "旧知识单元", "保留理解", 0, "complete", 85,
                            json.dumps(material, ensure_ascii=False), "2026-11-05 08:15:30.123456", 4, 2, 7,
                            "2026-11-02 08:15:30.123456", "2026-11-02 08:15:30.123456"))
        connection.execute("INSERT INTO learning_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("00000000-0000-4000-8000-000000000003", unit_id, "reflect", "过去的复盘内容",
                            "已有反馈", 80, "2026-11-01 08:15:30.123456"))
        connection.execute("INSERT INTO knowledge_entries VALUES (?, ?, ?, ?, ?, ?)",
                           ("00000000-0000-4000-8000-000000000004", "沉淀", "不能丢失的笔记", "reflection", unit_id,
                            "2026-11-01 08:15:30.123456"))
        connection.commit()
    engine, sessions = make_database(f"sqlite:///{path}")
    yield path, engine, sessions, unit_id
    engine.dispose()


def evidence_snapshot(engine):
    with engine.connect() as connection:
        return {name: [tuple(row) for row in connection.exec_driver_sql(f'SELECT * FROM "{name}" ORDER BY id')]
                for name in LEGACY_TABLES}


def test_new_database_and_repeated_startup(tmp_path):
    engine, _ = make_database(f"sqlite:///{tmp_path / 'fresh.db'}")
    try:
        assert initialize_database(engine) == CURRENT
        assert initialize_database(engine) == CURRENT
        assert set(inspect(engine).get_table_names()) == {*LEGACY_TABLES, "request_receipts", "alembic_version"}
    finally:
        engine.dispose()


def test_existing_unversioned_data_survives_upgrade(legacy):
    _, engine, sessions, unit_id = legacy
    before = evidence_snapshot(engine)
    assert initialize_database(engine) == CURRENT
    # Dates, JSON bytes, version counters, keys, feedback and every other original value are unchanged.
    assert evidence_snapshot(engine) == before
    with sessions() as session:
        unit = session.get(Unit, unit_id)
        assert unit.material["practice"]["correct_index"] == 1
        assert (unit.stage, unit.mastery, unit.review_count, unit.review_streak, unit.version) == ("complete", 85, 4, 2, 7)
        assert unit.review_due_at.isoformat() == "2026-11-05T08:15:30.123456"
        assert unit.completed_at.isoformat() == "2026-11-02T08:15:30.123456"
        assert unit.goal.title == "已有学习目标"
        assert unit.sessions[0].content == "过去的复盘内容"
        assert session.scalar(select(KnowledgeEntry)).content == "不能丢失的笔记"
    assert initialize_database(engine) == CURRENT
    assert evidence_snapshot(engine) == before


@pytest.mark.parametrize("change", [
    "ALTER TABLE units ADD COLUMN unknown TEXT",
    "DROP INDEX ix_units_stage",
    "CREATE TABLE unrelated (id INTEGER)",
    "CREATE VIEW custom_view AS SELECT id FROM goals",
    "CREATE INDEX custom_expression ON goals (lower(title))",
    "CREATE TRIGGER custom_trigger AFTER INSERT ON goals BEGIN UPDATE goals SET title='changed'; END",
])
def test_unrecognized_legacy_schema_is_never_stamped(legacy, change):
    _, engine, sessions, unit_id = legacy
    with engine.begin() as connection:
        connection.exec_driver_sql(change)
    with pytest.raises(MigrationError):
        initialize_database(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()
    assert "request_receipts" not in inspect(engine).get_table_names()
    with sessions() as session:
        assert session.get(Unit, unit_id).mastery == 85


def test_versioned_schema_drift_and_future_revision_are_rejected(legacy):
    _, engine, _, _ = legacy
    initialize_database(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='9999_future'"))
    with pytest.raises(MigrationError, match="unknown"):
        initialize_database(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "9999_future"
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num=:revision"), {"revision": CURRENT})
        connection.exec_driver_sql("ALTER TABLE units ADD COLUMN unexpected TEXT")
    with pytest.raises(MigrationError):
        initialize_database(engine)


def test_migration_failure_rolls_back_version_and_ddl(legacy, monkeypatch):
    _, engine, sessions, unit_id = legacy
    from app import migrations
    upgrade = migrations.command.upgrade

    def fail_after_upgrade(*args, **kwargs):
        upgrade(*args, **kwargs)
        raise RuntimeError("simulated failure after DDL")

    monkeypatch.setattr(migrations.command, "upgrade", fail_after_upgrade)
    with pytest.raises(RuntimeError, match="simulated"):
        initialize_database(engine)
    assert set(inspect(engine).get_table_names()) == set(LEGACY_TABLES)
    with sessions() as session:
        assert session.get(Unit, unit_id).sessions[0].content == "过去的复盘内容"


def test_invalid_relationships_block_upgrade(legacy):
    path, engine, _, _ = legacy
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE knowledge_entries SET unit_id='missing-unit'")
    with pytest.raises(MigrationError, match="foreign-key"):
        initialize_database(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()


def test_memory_database_supported():
    engine, _ = make_database("sqlite:///:memory:")
    try:
        assert initialize_database(engine) == CURRENT
        assert initialize_database(engine) == CURRENT
    finally:
        engine.dispose()
