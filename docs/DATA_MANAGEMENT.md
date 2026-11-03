# 数据升级、备份与恢复

本地学习数据默认在 `backend/data/doknow.db`。数据库包含目标、单元、题库与练习进度、学习记录及评价来源、知识笔记和提交回执；浏览器草稿另存于浏览器，不包含在数据库备份中。

以下命令从 `backend` 目录执行，使用 Python 3.11+。安装锁定依赖后，可以使用 `uv run --frozen python`，或将它替换为 Windows 的 `.venv\Scripts\python`、macOS / Linux 的 `.venv/bin/python`。

## 升级规则

应用启动会通过 Alembic 检查并升级数据库：

- 新数据库创建完整表结构，写入版本 `0003_learning_evidence`。
- 首版没有版本表的数据库，仅当四张表的列、类型、空值约束、主外键和索引与首版完全一致时，登记 `0001_baseline` 并升级。原有目标、课程材料、笔记和学习记录保留。
- 已有版本必须是应用认识的版本，结构也必须与该版本相符；不会把任意数据库标记成最新版。
- 未知表、额外列、缺少索引、自定义视图或 SQLite 触发器、无效外键、未知或较新版本会阻止启动，需要先调查或使用匹配版本的应用。
- SQLite 升级使用明确的写事务；PostgreSQL 使用事务与迁移锁。任何迁移失败都会回滚本次表结构与版本变化。

升级前先做备份。`0002_request_receipts` 增加提交回执表；`0003_learning_evidence` 在单元和学习记录表分别增加可空的练习进度、评价来源字段，不改写旧课程、旧回执或历史评分。旧评价显示“来源未知”，旧单题课程可继续学习；多题题库用于新建目标。不要直接修改 `alembic_version`，也不要使用 `stamp head` 跳过检查。自动丢弃旧库、破坏性降级均未提供。

可先手工运行与启动相同的检查和升级：

```powershell
uv run --frozen python -m app.data migrate
```

与后端一致，优先使用环境变量，再读取项目根目录 `.env` 与 `backend/.env` 中尚未设置的变量；未配置 `DATABASE_URL` 时使用当前目录下的 `data/doknow.db`。显式选择其他数据库：

```powershell
uv run --frozen python -m app.data migrate --database-url sqlite:///./data/another.db
```

应用与命令必须使用相同数据库地址。相对 SQLite 路径相对于命令工作目录，跨目录使用时应设置绝对路径，例如 `sqlite:///D:/DoKnowData/doknow.db`。

## 创建可校验的 SQLite 备份

先建立一个保存备份的目录。学习数据是私人内容，目录应在版本控制之外。项目中的 `backend/data/` 已被忽略：

```powershell
New-Item -ItemType Directory -Force data/backups
uv run --frozen python -m app.data backup --output data/backups/before-upgrade-2026-11-03.db
```

工具使用 SQLite 的在线 backup API，包含已提交的 WAL 数据；不只是复制 `.db` 主文件。备份生成独立数据库文件，并检查 SQLite 完整性、外键关系、DoKnow 结构、版本和各表记录数。输出 JSON 中包含目标路径、版本和记录数，退出码 `0` 才表示成功。

备份可以在本地后端运行时创建；备份是一致性快照，不包含尚未提交的事务，也不包含备份完成之后的操作。现有目标文件或 SQLite 侧文件存在时，命令会拒绝覆盖；每次选一个新文件名。

单独校验备份，不升级它：

```powershell
uv run --frozen python -m app.data verify --input data/backups/before-upgrade-2026-11-03.db
```

校验成功不代表备份包含所有你预期的业务记录；仍应检查返回的记录数，并在恢复后的页面中核对需要保留的目标与笔记。损坏、未知版本或不兼容结构均会返回非零退出码。

## 恢复到新数据库

恢复**只允许新路径**，不提供覆盖正在使用的数据库的选项。这样可以保留原文件，也不会把恢复结果与旧 WAL 混用。

1. 校验备份，然后恢复到一个不存在的新文件。源备份和恢复后的快照都会检查。

   ```powershell
   uv run --frozen python -m app.data restore --input data/backups/before-upgrade-2026-11-03.db --database-url sqlite:///./data/recovered-2026-11-03.db
   ```

2. 停止后端。将 `backend/.env` 中的 `DATABASE_URL` 改为恢复文件的地址，或在启动后端的同一终端设置它：

   ```powershell
   $env:DATABASE_URL = 'sqlite:///./data/recovered-2026-11-03.db'
   uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

3. 页面中核对目标、笔记、学习历史和复习日期。旧版备份会在启动时按照上述迁移规则升级。原数据库和备份仍保留，不自动清理。

恢复不修改原文件。若核对结果不符合预期，停止后端并切回原数据库地址，继续调查备份时间与内容。不要在后端运行时替换数据库文件、删除 WAL 或执行人工覆盖操作。

## PostgreSQL 与运行边界

迁移代码支持 PostgreSQL，Docker 的持久卷继续保存其学习数据。上述 `backup`、`restore`、`verify` 命令只处理文件型 SQLite；遇到 PostgreSQL 地址会明确拒绝，不会将 SQLite 命令套用到容器数据。

PostgreSQL 备份恢复应使用对应版本的 `pg_dump` / `pg_restore`，在独立数据库演练后再切换服务。本次没有运行 Docker / PostgreSQL 容器，不能把 SQLite 测试结果当作 PostgreSQL 实跑验证。

验证覆盖临时 SQLite 数据库的首版升级、重复启动、未知结构与较新版本拒绝、迁移失败回滚、已提交 WAL 备份、未提交数据排除、恢复保留内容、损坏备份拒绝和已有文件保护。没有对用户正式数据库执行升级或恢复演练。

参考：[Alembic Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html)、[Python sqlite3 backup](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)。
