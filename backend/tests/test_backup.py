"""WAL-aware backups and restoration never overwrite an existing learner database."""

from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from app.data import DataError, backup_database, inspect_backup, main, restore_database
from app.database import make_database
from app.migrations import CURRENT, initialize_database
from app.models import Goal


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "learner.db"
    url = f"sqlite:///{path}"
    engine, sessions = make_database(url)
    initialize_database(engine)
    with sessions() as session:
        session.add(Goal(title="重要学习目标", motivation="保留学习经历", daily_minutes=30))
        session.commit()
    yield path, url, engine
    engine.dispose()


def test_backup_includes_committed_wal_and_restore_preserves_data(database, tmp_path):
    path, url, _ = database
    with closing(sqlite3.connect(path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE goals SET title='刚写入 WAL 的学习目标'")
        writer.commit()
        assert Path(str(path) + "-wal").exists()
        backup = tmp_path / "snapshot.db"
        result = backup_database(url, backup)
        assert result["revision"] == CURRENT
        assert result["rows"]["goals"] == 1
        assert not Path(str(backup) + "-wal").exists()
        writer.execute("UPDATE goals SET title='备份后的新内容'")
        writer.commit()
        restored = tmp_path / "recovered.db"
        restore_database(backup, f"sqlite:///{restored}")
        with closing(sqlite3.connect(restored)) as connection:
            assert connection.execute("SELECT title FROM goals").fetchone() == ("刚写入 WAL 的学习目标",)
        assert inspect_backup(restored)["rows"] == result["rows"]
        assert writer.execute("SELECT title FROM goals").fetchone() == ("备份后的新内容",)


def test_existing_destinations_and_sidecars_are_never_replaced(database, tmp_path):
    _, url, _ = database
    destination = tmp_path / "keep.db"
    destination.write_bytes(b"do not replace this file")
    with pytest.raises(DataError, match="already exist"):
        backup_database(url, destination)
    assert destination.read_bytes() == b"do not replace this file"
    snapshot = tmp_path / "valid-backup.db"
    backup_database(url, snapshot)
    with pytest.raises(DataError, match="already exist"):
        restore_database(snapshot, url)
    another = tmp_path / "sidecar.db"
    Path(str(another) + "-wal").write_bytes(b"live database")
    with pytest.raises(DataError, match="sidecars"):
        backup_database(url, another)
    assert not another.exists()


@pytest.mark.parametrize("kind", ["corrupt", "unknown", "future"])
def test_invalid_backup_does_not_leave_restored_database(tmp_path, kind, database):
    _, url, _ = database
    source = tmp_path / "invalid.db"
    if kind == "corrupt":
        source.write_bytes(b"this is not a sqlite database")
    elif kind == "unknown":
        with closing(sqlite3.connect(source)) as connection:
            connection.execute("CREATE TABLE unrelated (id INTEGER)")
    else:
        backup_database(url, source)
        with closing(sqlite3.connect(source)) as connection:
            connection.execute("UPDATE alembic_version SET version_num='9999_future'")
            connection.commit()
    content = source.read_bytes()
    destination = tmp_path / "must-not-remain.db"
    with pytest.raises(DataError):
        restore_database(source, f"sqlite:///{destination}")
    assert not destination.exists()
    assert source.read_bytes() == content


def test_verify_is_readonly_and_cli_errors_are_nonzero(database, tmp_path, capsys):
    path, url, _ = database
    snapshot = tmp_path / "verified.db"
    backup_database(url, snapshot)
    content = snapshot.read_bytes()
    assert main(["verify", "--input", str(snapshot)]) == 0
    assert snapshot.read_bytes() == content
    assert main(["backup", "--database-url", url, "--output", str(path)]) == 1
    assert "Source and destination must differ" in capsys.readouterr().err
    assert main(["restore", "--input", str(snapshot), "--database-url", "postgresql://secret:password@db/private"]) == 1
    output = capsys.readouterr().err
    assert "password" not in output
    assert "file-backed SQLite" in output


def test_uncommitted_changes_are_not_copied(database, tmp_path):
    path, url, _ = database
    with closing(sqlite3.connect(path)) as writer:
        writer.execute("UPDATE goals SET title='尚未提交，不应进入备份'")
        snapshot = tmp_path / "committed-only.db"
        backup_database(url, snapshot)
        with closing(sqlite3.connect(snapshot)) as connection:
            assert connection.execute("SELECT title FROM goals").fetchone() == ("重要学习目标",)
        writer.rollback()


def test_unversioned_backup_can_be_restored_and_upgraded(tmp_path):
    original = tmp_path / "v0.1.db"
    with closing(sqlite3.connect(original)) as connection:
        connection.executescript((Path(__file__).parent / "fixtures/v0_1_schema.sql").read_text(encoding="utf-8"))
        connection.execute("INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?)",
                           ("00000000-0000-4000-8000-000000000001", "首版目标", "保留", "beginner", 30,
                            "2026-11-02 08:00:00.000000"))
        connection.commit()
    snapshot = tmp_path / "v0.1-backup.db"
    assert backup_database(f"sqlite:///{original}", snapshot)["revision"] == "unversioned-v0.1"
    recovered = tmp_path / "v0.1-restored.db"
    restore_database(snapshot, f"sqlite:///{recovered}")
    engine, sessions = make_database(f"sqlite:///{recovered}")
    try:
        assert initialize_database(engine) == CURRENT
        with sessions() as session:
            assert session.get(Goal, "00000000-0000-4000-8000-000000000001").title == "首版目标"
    finally:
        engine.dispose()
    assert inspect_backup(snapshot)["revision"] == "unversioned-v0.1"
