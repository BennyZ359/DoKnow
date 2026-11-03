"""Diagnostics inspect evidence without initializing, migrating or changing the source."""

import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.database import make_database
from app.diagnostics import inspect_database, mode_check, runtime_report, safe_provider_status
from app.migrations import CURRENT, initialize_database


def snapshot(directory):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir() if p.is_file()}


def test_missing_database_does_not_create_parent(tmp_path):
    path = tmp_path / "absent" / "db.sqlite"
    assert inspect_database(f"sqlite:///{path}")["status"] == "pending"
    assert not path.parent.exists()


@pytest.mark.parametrize("kind", ["empty", "baseline", "current", "unknown", "corrupt", "wrong_shape"])
def test_offline_inspection_preserves_every_byte_and_timestamp(tmp_path, kind):
    path = tmp_path / "test.db"
    if kind == "corrupt":
        path.write_bytes(b"not a database")
    elif kind == "baseline":
        with sqlite3.connect(path) as db:
            db.executescript((Path(__file__).parent / "fixtures/v0_1_schema.sql").read_text())
    else:
        engine, _ = make_database(f"sqlite:///{path}")
        if kind != "empty":
            initialize_database(engine)
            if kind == "unknown":
                with engine.begin() as db:
                    db.execute(text("UPDATE alembic_version SET version_num='secret-user:secret-pass@host'"))
            if kind == "wrong_shape":
                with engine.begin() as db:
                    db.execute(text("CREATE TABLE alien (id INTEGER)"))
        else:
            with engine.connect():
                pass
        engine.dispose()
    before = snapshot(tmp_path)
    result = inspect_database(f"sqlite:///{path}")
    assert result["status"] == {"empty": "pending", "baseline": "warning", "current": "ok"}.get(kind, "error")
    assert snapshot(tmp_path) == before
    assert "secret" not in json.dumps(result)


def test_wal_is_included_without_touching_source_sidecars(tmp_path):
    path = tmp_path / "test.db"
    engine, _ = make_database(f"sqlite:///{path}")
    try:
        initialize_database(engine)
        with engine.connect() as db:
            assert Path(str(path) + "-wal").stat().st_size > 0
            before = snapshot(tmp_path)
            result = inspect_database(f"sqlite:///{path}")
            assert result["revision"] == CURRENT
            assert snapshot(tmp_path) == before
            db.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def test_snapshot_concurrent_change_is_not_reported_as_healthy(tmp_path, monkeypatch):
    from app import diagnostics
    path = tmp_path / "test.db"
    path.touch()
    original = diagnostics.shutil.copyfile

    def changed(source, target):
        original(source, target)
        path.write_bytes(b"changed")

    monkeypatch.setattr(diagnostics.shutil, "copyfile", changed)
    assert inspect_database(f"sqlite:///{path}")["status"] == "error"


@pytest.mark.parametrize("url", ["invalid://user:secret@host", "postgresql://user:secret@[invalid", "not a url secret"])
def test_invalid_urls_never_expose_credentials(url):
    result = inspect_database(url)
    assert result["status"] == "error"
    assert "secret" not in json.dumps(result)


def test_mode_is_local_validation_only(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    assert mode_check()["status"] == "ok"
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "private-token")
    monkeypatch.setenv("AI_BASE_URL", "https://user:private-token@example.com/v1")
    assert mode_check()["status"] == "error"
    monkeypatch.setenv("AI_MODEL", "private-token")
    assert safe_provider_status()["model"] == "名称已隐藏"
    monkeypatch.setenv("AI_PROVIDER", "https://user:private-token@example.com")
    assert safe_provider_status()["provider"] == "unknown"
    assert "private-token" not in json.dumps(safe_provider_status())


def test_runtime_endpoint_safe_degraded_response_and_no_migration(tmp_path, monkeypatch):
    from app.main import create_app
    monkeypatch.setenv("AI_PROVIDER", "demo")
    application = create_app(f"sqlite:///{tmp_path / 'runtime.db'}")
    with TestClient(application) as client:
        before = snapshot(tmp_path)
        response = client.get("/api/diagnostics")
        assert response.headers["cache-control"] == "no-store"
        report = response.json()
        assert report["read_only"] and report["status"] == "ok"
        assert report["checks"][-1]["revision"] == CURRENT
        assert snapshot(tmp_path) == before
        with application.state.engine.begin() as db:
            db.execute(text("DROP TABLE knowledge_entries"))
        before = snapshot(tmp_path)
        report = client.get("/api/diagnostics").json()
        assert report["status"] == "error"
        assert snapshot(tmp_path) == before


def test_runtime_connection_error_is_sanitized():
    class Broken:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def connect(self):
            raise RuntimeError("postgresql://user:secret@host/private")

    report = runtime_report(Broken())
    assert report["status"] == "error"
    assert "secret" not in json.dumps(report)
