# DoKnow 开发交接

更新日期：2026-11-03（Asia/Shanghai）。先核对实际 Git 状态，再读 [进度记录](PROGRESS.md)。

## 当前状态

P0、P1-1 评价历史、P1-2 多题与错题巩固、P1-4 笔记管理和 P1-3 目标基础编辑已交付。本轮从 `6eb33927bca6ac60a5dea9a4161eab5ae1e01325` 开始，已核对工作区干净、远端一致，基线 [CI 41580247743](https://github.com/BennyZ359/DoKnow/actions/runs/41580247743) 成功。

本轮实现 **P1-6 启动与诊断，以及相关 P1-8 交互修正**：

- 项目根目录 `doknow.ps1` 提供 start/stop/diagnose；跨平台标准库入口是 `scripts/local.py`。
- Windows 监督进程以 Job Object 管理自己启动的整组服务，子进程门控防止登记前逃逸；重复启动不创建第二组，端口冲突不杀占用者，失败会收尾已启动服务。
- `--demo` 使用 `.cache/local/demo.db`，覆盖模型为 demo、禁用 Redis。默认 start 沿用环境配置和学习库，仍会按原有规则迁移，使用前先备份。
- 离线与设置页诊断不会建库或升级。SQLite 使用包含 WAL 的临时副本，源数据库与侧文件不变。PostgreSQL 使用只读事务和超时，但实际容器尚未验证。
- 设置页由 `SettingsView.vue`、`RuntimeStatus.vue` 承担，支持键盘刷新、焦点、失败重试及手机布局。设置页不再等待学习概览数据读取，服务异常时仍可查看诊断指引。
- 新增 `/api/diagnostics`；设置/诊断只输出安全字段，不返回密钥、含凭据地址、原始异常或学习正文。

本轮完整回归及提交/CI 状态以 [PROGRESS.md](PROGRESS.md) 顶部为准。新增 Windows CI 后共五项任务（backend、frontend、browser、compose、local-windows）；按最终实际 SHA 查询，不能用基线或功能提交的成功代替后续提交。

## 项目位置与运行

- 实际仓库：`D:\Project\learn-agent\DoKnow`。父目录 learn-agent 另有空 Git 仓库，不要在父目录提交。
- 分支：`develop`；远端：`origin`，`BennyZ359/DoKnow`。
- 后端环境：`backend/.venv`。数据库版本仍为 `0004_editable_records`，本轮没有新迁移，正式学习库未升级。
- 运行与排障：[LOCAL_RUNNING.md](LOCAL_RUNNING.md)；数据保护：[DATA_MANAGEMENT.md](DATA_MANAGEMENT.md)。
- Windows 示例：`.\doknow.ps1 start --demo`、`.\doknow.ps1 diagnose --demo`、`.\doknow.ps1 stop`。
- `.cache/local/state.json` 包含本机控制令牌，不提交或分享。`events.log` 只包含安全阶段信息；原始进程输出不持久保存。

## 下轮范围

P1-6 与本轮相关 P1-8 已实现，不要重复开发启停和状态页。下一轮可单独设计 P1-3 剩余的课程重生成、难度调整、单元重排，明确变更如何保留已有学习证据。真实模型与容器分别依赖用户模型配置/费用范围和运行中的 Docker，继续列为未验证，不自动纳入。

默认继续使用 demo、模拟模型、独立测试数据库。保留正式学习资料，不调用付费模型，不启动 Docker。任何新的诊断代码不得隐式初始化或迁移数据库；任何新的进程管理不得根据端口或过期 PID 结束未知进程。

## 恢复工作与代码入口

1. 阅读本文、`PROGRESS.md`、`ROADMAP.md`、`API_CONTRACT.md`。
2. 核对工作目录、HEAD、分支、工作区、远端与 HEAD 的 CI。历史记录只作参考。
3. 数据库诊断：`backend/app/diagnostics.py`；现有迁移：`backend/app/migrations/`；接口：`backend/app/main.py`。
4. 本地进程：`scripts/local.py`、`scripts/processes.py`；测试：`backend/tests/test_local_launcher.py`、`test_diagnostics.py`。
5. 前端：`frontend/src/components/SettingsView.vue`、`RuntimeStatus.vue`、`App.vue`；浏览器：`tests/browser/settings.spec.ts`。
6. 在进度顶部写明下一项正在做的可验收结果，完成后更新实际验证。

## 验证

后端目录：

```powershell
.venv/Scripts/python -m pytest -q
.venv/Scripts/ruff check app tests ../scripts
```

前端目录：

```powershell
npm run build
npm run format:check
```

浏览器目录：

```powershell
npm test
```

浏览器使用独立 SQLite、8001/5174 端口，不连接正式数据库。同一时间只运行一个 runner。当前本机 Windows Playwright 的 webServer 收尾可能等待其服务进程；若用例已结束而 runner 未退出，先依据本次日志核对本次启动的确切进程，再停止它们并取得最终汇总。不要按端口批量杀进程。新的本地启动工具已有独立的正常停止及异常清理测试，不能把 Playwright 收尾问题混作产品启停失败。

根目录检查 `docker --config .cache/docker compose config --quiet`（仅静态，不启动引擎）、`git diff --check`、Markdown 本地链接。CI 的 Windows 任务也运行真实 demo 启停与诊断。

## Git 与数据规则

每次 Git 写操作前核对目录、分支和暂存差异，按文件暂存。沿用 develop，普通推送；不强推、不重写历史、不向 main 发布。远端有新提交时先比较，不能覆盖。Windows 凭据存储可能需要受控执行，使用现有授权，不打印或导出凭据。

`.env`、`backend/data/`、备份、`.cache/`、依赖与浏览器输出均不得提交。实际学习库的升级、恢复和容器验证需要在独立备份/测试库先验证。
