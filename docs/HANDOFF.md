# DoKnow 开发交接

更新日期：2026-11-03（Asia/Shanghai）。先读本文，再读 [进度记录](PROGRESS.md)。功能是否完成以进度记录和实际验证为准。

## 当前目标

用户选择先完善**个人本地版**：保留“学 → 练 → 实战 → 讲解 → 复盘 → 间隔复习”的学习闭环，先解决使用过程中丢输入、结果不明确和数据难以恢复的问题。

本轮范围包括五项：数据库版本迁移、备份恢复、草稿保存、提交恢复、复习到期刷新。完成后验证、提交和推送。多用户、公网部署、OCR、向量检索、执行用户代码属于后续路线，见 [路线图](ROADMAP.md)。

**本轮五项已完成**：后端 89 项、浏览器 14 项通过。继续工作请先核对 `PROGRESS.md` 和 Git 状态，再决定下一轮 P1 范围。

**本轮五个提交已推送到 `origin/develop`**，代码版本为 `947924e`。对应 [CI 运行 41554189256](https://github.com/BennyZ359/DoKnow/actions/runs/41554189256) 的后端、前端、浏览器及 Compose 静态检查全部成功。之前的推送阻塞已解除；后续若有新提交，应核对该提交自己的 CI。

## 项目位置与版本

- 实际仓库：`D:\Project\learn-agent\DoKnow`。父目录 `D:\Project\learn-agent` 另有一个空 Git 仓库，不要在父目录提交。
- 当前开发分支：`develop`；远程：`origin`，仓库 `BennyZ359/DoKnow`。
- 首版基线：`53bf275c1769f7cf8af6e758d37cf740c0110aa5`。本轮开始时与远端 `develop` 一致。
- 本轮开始前检查：54 项后端测试、Ruff、前端生产构建与格式检查通过；首版 CI 全部通过。后续结果记入 `PROGRESS.md`，不要把历史测试结果当作修改后的验证。
- Python 环境在 `backend/.venv`；Node、uv、Chrome 和 npm 依赖已安装。

## 阅读顺序和代码入口

1. `README.md`：启动、产品能力与部署边界。
2. `docs/PROGRESS.md`：已完成项、在做事项、验证和阻塞。
3. `docs/ROADMAP.md`：下一批工作与验收标准。
4. `docs/LEARNING_DESIGN.md`：学习理念与阶段约束。
5. `docs/ARCHITECTURE.md`、`docs/API_CONTRACT.md`：数据和接口边界。
6. `backend/app/main.py`、`models.py`、`database.py`、`serialization.py`：接口、证据记录、并发和序列化。
7. `backend/app/services/`：课程规划、导师、评价、文档检索与模型适配。
8. `frontend/src/App.vue`、`api.ts` 及新增的状态模块；`tests/browser/`：学习交互与浏览器回归。

## 不需要用户熬夜配合的默认选择

- 使用 demo 模式和独立测试数据库完成本轮任务，不需要模型密钥。
- 本轮开始时项目根目录和 `backend/` 均无 `.env`；Docker 引擎未运行。它们不阻塞五项本地任务。
- 不改变用户正式学习数据；迁移和恢复实验先使用临时数据库或备份副本。
- 没有真实模型或 Docker 时，记录“未验证”，继续完成其他工作。
- 保留 SQLite 单人本地运行和 Docker/PostgreSQL 配置，不将本轮当作多人服务发布。

## Git 操作

操作约定：

- 每次写 Git 前核对工作目录、分支、工作区和暂存差异。按具体文件暂存，保留已有无关修改。
- 沿用 `develop`，不自动向 `main` 发布；不强制推送、不重写历史、不删除用户分支。
- 如果远端发生变化，先读取与比较，不能用强推覆盖。需要人工才能解决时记录阻塞，保留本地成果。
- 本次使用现有配置成功推送；无需再套用历史的禁用代理方案。
- Windows 凭据存储可能需要受控执行。使用现有授权完成普通提交和推送；审批拒绝时保留结果并说明原因，不导出、打印或另存凭据。
- `.env`、`backend/data/`、备份、`.cache/`、依赖和浏览器输出都不能加入提交。

## 连续工作的执行方式

先更新 `PROGRESS.md` 的“正在做”，以一项可验证的结果为单位推进。每项完成记录变更、测试命令、实际结果和剩余限制，随后继续下一项。会话压缩或中断后，从该文件恢复，不从头重做。

电脑需保持供电、网络可用且不休眠，Codex 保持打开。本轮环境使用受限文件系统和自动审批；仓库文档无法改变这些权限。用户授权也不保证凭据、网络、额度、审批服务或电脑状态整晚可用。遇到环境阻塞先完成不依赖它的任务，在进度中留下具体原因；不要为了无人值守关闭权限控制。

本轮是当前会话内持续开发，没有创建定时任务、新会话或循环自动化。完成五项验收及提交推送后即可交付，不为凑满一晚继续扩大范围。

## 验证方式

各命令在标注的目录执行。每一步失败都应处理或记录，不要让后一个成功命令掩盖前一个失败。

后端（`backend/`）：

```powershell
uv sync --frozen --extra dev
uv run --frozen pytest -q
uv run --frozen ruff check app tests
```

前端（`frontend/`）：

```powershell
npm ci
npm run build
npm run format:check
```

浏览器（`tests/browser/`）：

```powershell
npm ci
npm test
```

浏览器测试使用独立 SQLite 文件及 8001/5174 端口，不要指向正式 `backend/data/doknow.db`。同一时间只运行一个浏览器测试进程。需要验证复习时间时，只调整测试时钟或测试数据库。

项目根目录：

```powershell
docker compose config --quiet
git diff --check
git status --short --branch
```

实际 Docker 验证需运行中的引擎。真实模型联调留给后续：用户配置服务地址、模型名和服务端密钥，并给出明确费用范围后再运行少量测试，不把密钥写入聊天或仓库。首版的模型请求模拟测试不等于真实服务联调。

## 用户离开前需要做什么

本轮五项任务已交付，无需额外配置账号、模型密钥或启动 Docker。

以后要验证真实模型：在 `backend/.env` 中设置模型服务并说明允许的测试范围和费用；以后要验证 Docker：先启动 Docker Desktop。二者可在用户醒来后安排，不应阻塞本轮交付。
