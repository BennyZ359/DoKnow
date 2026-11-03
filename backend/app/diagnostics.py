"""Read-only, allowlisted runtime reports. Never import app.main or make_database."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from .migrations import BASELINE, CURRENT, VERSION_TABLE, metadata_for_revision, validate_schema
from .services.providers import provider_status


def check(name: str, status: str, detail: str, action: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, "action": action}


def safe_provider_status() -> dict:
    status = provider_status()
    status["provider"] = status["provider"] if status["provider"] in {"demo", "openai", "compatible"} else "unknown"
    model = status["model"]
    if status["mode"] != "demo" and (
        not re.fullmatch(r"[a-zA-Z0-9_./-]{1,200}", model)
        or (os.getenv("AI_API_KEY") and os.environ["AI_API_KEY"] in model)
        or model.startswith("sk-")
    ):
        status["model"] = "名称已隐藏"
    return status


def mode_check() -> dict:
    status = safe_provider_status()
    if status["mode"] == "demo":
        return check("mode", "ok", "体验模式，无需密钥；未调用模型。")
    return check("mode", "ok" if status["configured"] else "error",
                 "AI 配置已填写，连通性未验证。" if status["configured"] else "AI 配置不完整或格式无效。",
                 "检查服务端 AI_PROVIDER、AI_BASE_URL、AI_MODEL、AI_API_KEY；诊断不会调用模型。")


def database_check(connection) -> dict:
    names = set(inspect(connection).get_table_names())
    if not names:
        return check("database", "pending", "数据库为空，尚未初始化。", "启动服务时才会初始化；诊断不会建表。")
    versioned = VERSION_TABLE in names
    revision = BASELINE
    if versioned:
        revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if len(revisions) != 1 or revisions[0] not in {
            BASELINE, "0002_request_receipts", "0003_learning_evidence", CURRENT,
        }:
            return check("database", "error", "数据库版本未知或不明确。", "保留原库，使用匹配的应用版本；不要手工修改版本表。")
        revision = revisions[0]
    validate_schema(connection, metadata_for_revision(revision), versioned=versioned)
    current = versioned and revision == CURRENT
    return check("database", "ok" if current else "warning",
                 f"当前版本：{revision if versioned else 'unversioned-v0.1'}；应用要求：{CURRENT}。",
                 "" if current else "先按 docs/DATA_MANAGEMENT.md 备份，再启动服务进行升级。") | {
                     "revision": revision if versioned else "unversioned-v0.1", "expected_revision": CURRENT,
                 }


def database_failure() -> dict:
    return check("database", "error", "数据库无法读取或结构不兼容。",
                 "检查文件权限、数据库服务及连接配置；保留原库，按 docs/DATA_MANAGEMENT.md 校验备份。")


@contextmanager
def sqlite_snapshot(path: Path):
    """Copy main/WAL into scratch space: even SQLite SHM creation stays off the source.

    Refuse a moving snapshot. No immutable=1 shortcut, which would ignore committed WAL.
    """
    sources = [path, Path(str(path) + "-wal"), Path(str(path) + "-journal")]

    def signatures():
        return [(p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in sources]

    with tempfile.TemporaryDirectory(prefix="doknow-diagnose-") as directory:
        target = Path(directory) / "snapshot.db"
        before = signatures()
        for source, signature, suffix in zip(sources, before, ("", "-wal", "-journal")):
            if signature is not None:
                shutil.copyfile(source, str(target) + suffix)
        if signatures() != before:
            raise RuntimeError("Database changed during snapshot")
        engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(
            target.as_uri() + "?mode=ro", uri=True, timeout=2,
        ))
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA query_only=ON")
                yield connection
        finally:
            engine.dispose()


def inspect_database(database_url: str) -> dict:
    engine = None
    try:
        url = make_url(database_url)
        if url.get_backend_name() == "sqlite":
            if not url.database or url.database == ":memory:" or url.query:
                return check("database", "warning", "此地址不支持离线诊断。", "文件型 SQLite 请使用无查询参数的地址；内存库在运行页面查看。")
            path = Path(url.database).resolve()
            if not path.exists():
                return check("database", "pending", "数据库文件尚不存在。", "启动服务时才会创建；诊断不会创建目录或文件。")
            with sqlite_snapshot(path) as connection:
                return database_check(connection)
        if url.get_backend_name() != "postgresql":
            return check("database", "error", "不支持的数据库类型。", "使用 SQLite 或 PostgreSQL。")
        engine = create_engine(url, connect_args={"connect_timeout": 3, "options": "-c default_transaction_read_only=on -c statement_timeout=3000"})
        with engine.connect() as connection:
            return database_check(connection)
    except Exception:
        # Exceptions may contain URLs, passwords, SQL or arbitrary version strings.
        return database_failure()
    finally:
        if engine is not None:
            engine.dispose()


def runtime_report(engine) -> dict:
    try:
        if engine.dialect.name == "sqlite" and engine.url.database not in (None, "", ":memory:"):
            database = inspect_database(engine.url.render_as_string(hide_password=False))
        else:
            with engine.connect() as connection:
                if engine.dialect.name == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    connection.exec_driver_sql("SET LOCAL statement_timeout=3000")
                database = database_check(connection)
    except Exception:
        database = database_failure()
    checks = [check("backend", "ok", "后端已响应。"), mode_check(), database]
    return {"status": "error" if any(c["status"] == "error" for c in checks) else "ok",
            "mode": safe_provider_status()["mode"], "database": engine.dialect.name,
            "checks": checks, "read_only": True}


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    checks = [mode_check(), inspect_database(os.getenv("DATABASE_URL", "sqlite:///./data/doknow.db"))]
    print(json.dumps({"checks": checks, "read_only": True}, ensure_ascii=True))
    return int(any(c["status"] == "error" for c in checks))


if __name__ == "__main__":
    raise SystemExit(main())
