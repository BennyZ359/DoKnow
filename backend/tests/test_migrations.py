"""Upgrade genuine v0.1 evidence, reject unknown schemas, and roll back failed DDL."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import inspect, select, text

from app.database import make_database
from app.migrations import CURRENT, MigrationError, configuration, initialize_database
from app.migrations.schema import baseline_metadata
from app.models import KnowledgeEntry, LearningSession, Unit


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
    columns = {name: ", ".join(f'"{column.name}"' for column in table.columns)
               for name, table in baseline_metadata().tables.items()}
    with engine.connect() as connection:
        return {name: [tuple(row) for row in connection.exec_driver_sql(f'SELECT {columns[name]} FROM "{name}" ORDER BY id')]
                for name in LEGACY_TABLES}


def test_new_database_and_repeated_startup(tmp_path):
    engine, _ = make_database(f"sqlite:///{tmp_path / 'fresh.db'}")
    try:
        assert initialize_database(engine) == CURRENT
        assert initialize_database(engine) == CURRENT
        assert set(inspect(engine).get_table_names()) == {*LEGACY_TABLES, "request_receipts", "course_changes", "roadmaps", "concept_graphs", "knowledge_entities", "knowledge_relations", "alembic_version"}
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
        assert session.scalar(select(Unit.mastery).where(Unit.id == unit_id)) == 85


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
        assert session.scalar(select(LearningSession.content).where(LearningSession.unit_id == unit_id)) == "过去的复盘内容"


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


@pytest.mark.parametrize("fail", [False, True])
def test_receipt_revision_upgrade_preserves_every_existing_value(legacy, monkeypatch, fail):
    path, engine, sessions, unit_id = legacy
    # Freeze the prior revision independently from the new application models.
    with sqlite3.connect(path) as connection:
        connection.executescript('''
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
            INSERT INTO alembic_version VALUES ('0002_request_receipts');
            CREATE TABLE request_receipts (
                key VARCHAR(128) NOT NULL PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL,
                owner_token VARCHAR(36) NOT NULL, status VARCHAR(16) NOT NULL,
                lease_until DATETIME NOT NULL, response_status INTEGER, response_body TEXT,
                created_at DATETIME NOT NULL, completed_at DATETIME, resource_scope VARCHAR(80)
            );
            INSERT INTO request_receipts VALUES (
                'original-key', 'fingerprint', 'owner', 'completed', '2026-11-01 00:00:00',
                200, '{"feedback":"original result"}', '2026-11-01 00:00:00',
                '2026-11-01 00:00:00', 'goal:existing'
            );
        ''')
    before = evidence_snapshot(engine)
    with engine.connect() as connection:
        receipt = connection.exec_driver_sql("SELECT * FROM request_receipts").all()
    if fail:
        from app import migrations
        original = migrations.command.upgrade

        def fail_after_columns(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("failure after new columns")

        monkeypatch.setattr(migrations.command, "upgrade", fail_after_columns)
        with pytest.raises(RuntimeError, match="new columns"):
            initialize_database(engine)
        assert "practice_state" not in {column["name"] for column in inspect(engine).get_columns("units")}
        assert "assessment" not in {column["name"] for column in inspect(engine).get_columns("learning_sessions")}
    else:
        assert initialize_database(engine) == CURRENT
        assert initialize_database(engine) == CURRENT
        with sessions() as session:
            assert session.get(Unit, unit_id).practice_state is None
            assert session.scalar(select(LearningSession)).assessment is None
    assert evidence_snapshot(engine) == before
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT * FROM request_receipts").all() == receipt
        revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        assert revision == ("0002_request_receipts" if fail else CURRENT)


@pytest.mark.parametrize("fail", [False, True])
def test_learning_revision_upgrade_preserves_evidence_and_receipts(legacy, monkeypatch, fail):
    _, engine, sessions, unit_id = legacy
    from app import migrations
    # Build the actual prior revision, then capture every column as raw SQL values.
    with engine.begin() as connection:
        config = configuration()
        config.attributes["connection"] = connection
        migrations.command.stamp(config, "0001_baseline")
        migrations.command.upgrade(config, "0003_learning_evidence")
        connection.execute(text("UPDATE units SET practice_state=:value"), {"value": '{"round":2,"attempt":4,"completed":["q1"]}'})
        connection.execute(text("UPDATE learning_sessions SET assessment=:value"), {"value": '{"source":"demo","passed":true,"rule_version":"previous"}'})
        connection.exec_driver_sql("""INSERT INTO request_receipts VALUES (
            'prior-request', 'fingerprint', 'owner', 'complete', '2026-11-01 00:00:00',
            200, '{"feedback":"original receipt"}', '2026-11-01 00:00:00',
            '2026-11-01 00:00:00', 'goal:existing')""")
    names = (*LEGACY_TABLES, "request_receipts")
    columns = {name: ', '.join(f'"{column["name"]}"' for column in inspect(engine).get_columns(name)) for name in names}

    def snapshot():
        with engine.connect() as connection:
            return {name: connection.exec_driver_sql(f'SELECT {columns[name]} FROM "{name}"').all() for name in names}

    before = snapshot()
    if fail:
        upgrade = migrations.command.upgrade

        def fail_after_upgrade(*args, **kwargs):
            upgrade(*args, **kwargs)
            raise RuntimeError("failed after editable columns")

        monkeypatch.setattr(migrations.command, "upgrade", fail_after_upgrade)
        with pytest.raises(RuntimeError, match="editable columns"):
            initialize_database(engine)
        assert "version" not in {column["name"] for column in inspect(engine).get_columns("goals")}
        assert "original" not in {column["name"] for column in inspect(engine).get_columns("knowledge_entries")}
    else:
        assert initialize_database(engine) == CURRENT
        assert initialize_database(engine) == CURRENT
        with sessions() as db:
            item = db.scalar(select(KnowledgeEntry))
            assert item.version == 1 and item.tags is None and item.original is None
            assert item.updated_at == item.created_at
            goal = db.get(Unit, unit_id).goal
            assert goal.version == 1 and goal.updated_at == goal.created_at
    assert snapshot() == before
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == ("0003_learning_evidence" if fail else CURRENT)


@pytest.mark.parametrize("fail", [False, True])
def test_editable_revision_upgrade_preserves_all_values_and_rolls_back(legacy, monkeypatch, fail):
    _, engine, sessions, unit_id = legacy
    from app import migrations
    with engine.begin() as connection:
        config = configuration()
        config.attributes["connection"] = connection
        migrations.command.stamp(config, "0001_baseline")
        migrations.command.upgrade(config, "0004_editable_records")
        connection.execute(text("UPDATE goals SET version=3"))
        connection.execute(text("UPDATE knowledge_entries SET version=4, tags=:tags, original=:original"),
                           {"tags": '["原标签"]', "original": '{"title":"原始标题","content":"原始证据"}'})
        connection.execute(text("UPDATE learning_sessions SET assessment=:value"), {"value": '{"source":"demo","passed":true}'})
        connection.execute(text("UPDATE units SET practice_state=:value"), {"value": '{"round":2,"attempt":4}'})
        connection.exec_driver_sql("""INSERT INTO request_receipts VALUES (
            'editable-receipt', 'fingerprint', 'owner', 'complete', '2026-11-01 00:00:00',
            200, '{"feedback":"original receipt"}', '2026-11-01 00:00:00',
            '2026-11-01 00:00:00', 'goal:existing')""")
    names = (*LEGACY_TABLES, "request_receipts")
    columns = {name: ', '.join(f'"{column["name"]}"' for column in inspect(engine).get_columns(name)) for name in names}
    def capture():
        with engine.connect() as connection:
            return {name: connection.exec_driver_sql(f'SELECT {columns[name]} FROM "{name}"').all() for name in names}
    before = capture()
    if fail:
        upgrade = migrations.command.upgrade
        def broken(*args, **kwargs):
            upgrade(*args, **kwargs)
            raise RuntimeError("course migration interrupted")
        monkeypatch.setattr(migrations.command, "upgrade", broken)
        with pytest.raises(RuntimeError, match="interrupted"):
            initialize_database(engine)
        assert "course_changes" not in inspect(engine).get_table_names()
        assert "archived" not in {column["name"] for column in inspect(engine).get_columns("units")}
        assert "course_version" not in {column["name"] for column in inspect(engine).get_columns("goals")}
    else:
        assert initialize_database(engine) == CURRENT
        assert initialize_database(engine) == CURRENT
        with sessions() as db:
            unit = db.get(Unit, unit_id)
            assert unit.archived == 0 and unit.goal.course_version == 1
            assert unit.version == 7 and unit.goal.version == 3
    assert capture() == before
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == ("0004_editable_records" if fail else CURRENT)


@pytest.mark.parametrize("fail", [False, True])
def test_roadmap_upgrade_keeps_course_evidence_and_rolls_back(legacy, monkeypatch, fail):
    _, engine, _, _ = legacy
    from app import migrations
    with engine.begin() as connection:
        config = configuration()
        config.attributes["connection"] = connection
        migrations.command.stamp(config, "0001_baseline")
        migrations.command.upgrade(config, "0005_course_changes")
    names = [name for name in inspect(engine).get_table_names() if name != "alembic_version"]
    def capture():
        with engine.connect() as connection:
            return {name: connection.exec_driver_sql(f'SELECT * FROM "{name}"').all() for name in names}
    before = capture()
    if fail:
        upgrade = migrations.command.upgrade
        def broken(*args, **kwargs):
            upgrade(*args, **kwargs)
            raise RuntimeError("roadmap migration interrupted")
        monkeypatch.setattr(migrations.command, "upgrade", broken)
        with pytest.raises(RuntimeError, match="interrupted"):
            initialize_database(engine)
        assert "roadmaps" not in inspect(engine).get_table_names()
    else:
        assert initialize_database(engine) == CURRENT
        assert "roadmaps" in inspect(engine).get_table_names()
    assert capture() == before
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == ("0005_course_changes" if fail else CURRENT)


@pytest.mark.parametrize("fail", [False, True])
def test_concept_graph_upgrade_preserves_existing_roadmaps(legacy, monkeypatch, fail):
    _, engine, _, _ = legacy
    from app import migrations
    with engine.begin() as connection:
        config = configuration()
        config.attributes["connection"] = connection
        migrations.command.stamp(config, "0001_baseline")
        migrations.command.upgrade(config, "0006_roadmaps")
        connection.exec_driver_sql("INSERT INTO roadmaps VALUES ('old-map', '已有主题', '{\"nodes\":[]}', '2026-11-03 00:00:00')")
    names = [name for name in inspect(engine).get_table_names() if name != "alembic_version"]
    def capture():
        with engine.connect() as connection:
            return {name: connection.exec_driver_sql(f'SELECT * FROM "{name}"').all() for name in names}
    before = capture()
    if fail:
        upgrade = migrations.command.upgrade
        def broken(*args, **kwargs):
            upgrade(*args, **kwargs)
            raise RuntimeError("concept migration interrupted")
        monkeypatch.setattr(migrations.command, "upgrade", broken)
        with pytest.raises(RuntimeError, match="interrupted"):
            initialize_database(engine)
        assert "knowledge_entities" not in inspect(engine).get_table_names()
    else:
        assert initialize_database(engine) == CURRENT
        assert {"concept_graphs", "knowledge_entities", "knowledge_relations"} <= set(inspect(engine).get_table_names())
    assert capture() == before
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == ("0006_roadmaps" if fail else CURRENT)
