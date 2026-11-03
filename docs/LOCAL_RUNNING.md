# 本地启动、停止与只读诊断

在实际 `DoKnow` 仓库操作。需要 Python 3.11+、Node.js 22+；后端依赖位于 `backend/.venv`，前端依赖位于 `frontend/node_modules`。入口不自动安装软件，不启动 Docker，不调用模型，不结束占用端口的其他进程。

## Windows 推荐入口

首次安装依赖：

```powershell
cd backend
uv sync --frozen --extra dev
cd ../frontend
npm ci
cd ..
```

无需模型配置的独立体验：

```powershell
.\doknow.ps1 diagnose --demo
.\doknow.ps1 start --demo
.\doknow.ps1 stop
```

打开启动结果中的地址，默认 [http://127.0.0.1:5173](http://127.0.0.1:5173)。服务在后台运行，不打开额外窗口；`stop` 后数据保留。`--demo` 强制体验模式、禁用 Redis、使用独立的 `.cache/local/demo.db`，不会访问正式学习库；再次启动继续使用该体验库。`.cache` 下内容不进入 Git，勿将它当作正式资料的长期存储位置。

如需使用已有学习数据，先按 [数据管理](DATA_MANAGEMENT.md) 备份，然后去掉 `--demo`：

```powershell
.\doknow.ps1 diagnose
.\doknow.ps1 start
.\doknow.ps1 stop
```

此时沿用应用配置优先级：当前环境变量 → 根目录 `.env` → `backend/.env` → 默认值。相对数据库路径以 **backend 目录**为基准；默认是 `backend/data/doknow.db`。`start` 的后端启动仍会执行已有的数据库初始化/迁移，**只有 diagnose 保证不升级或修改数据库**。AI 配置是否填写、格式是否有效，不代表真实模型连接已验证。

如果 PowerShell 执行策略不允许运行脚本，无需更改系统策略，直接运行等价的 Python 入口：

```powershell
backend\.venv\Scripts\python.exe scripts/local.py diagnose --demo
backend\.venv\Scripts\python.exe scripts/local.py start --demo
backend\.venv\Scripts\python.exe scripts/local.py stop
```

如果 `.venv` 尚未安装，可用现有 Python 3.11+ 执行 `python scripts/local.py diagnose`，它会报告缺失环境。macOS / Linux 使用 `backend/.venv/bin/python scripts/local.py ...`；Windows 是本轮主要实际验证环境，Linux 在 CI 验证进程测试。

## 体验课程调整

在 demo 模式新建一个目标，从学习页选择「调整课程与查看历史」（概览卡片也有入口）。选择重生成、难度或重排，先预览，再勾选确认。已保存聊天或学习记录的单元固定保留；预览后又产生学习记录时需重新预览。旧单元可从变更记录打开，只读显示原材料和原 ID 下的草稿。demo 重生成是确定性模板，同一难度可能得到相同内容。

应用数据库版本现在为 `0005_course_changes`。本轮只升级独立测试库，正式学习库未升级；去掉 `--demo` 前请先按 [数据管理](DATA_MANAGEMENT.md) 备份。课程预览和确认的网络失败可用「恢复」按钮确认原操作；不要为了恢复结果重复创建课程。完整规则见 [COURSE_ADJUSTMENTS.md](COURSE_ADJUSTMENTS.md)。

## 参数、重复启动与停止规则

```powershell
.\doknow.ps1 start --demo --backend-port 8016 --frontend-port 5186
.\doknow.ps1 diagnose --demo --backend-port 8016 --frontend-port 5186
.\doknow.ps1 stop
```

- 前后端只绑定 `127.0.0.1`；端口必须不同。前端代理自动指向所选后端端口，Vite 不会悄悄换端口。
- 同一仓库只管理一组服务。相同参数重复 `start` 返回已运行；不同端口或模式需先 `stop`。环境配置改变也需要先停止再启动。
- 默认每个服务最多等待 30 秒，可用 `--timeout 60` 调整（1–120 秒）。启动完成需后端健康检查和前端 `/api` 代理都通过。
- 缺依赖、不可读/不兼容数据库、端口占用会在启动前拒绝；启动中失败会收尾本次进程。新体验库可能已完成初始化，失败收尾保留它，便于恢复。
- Windows 使用 Job Object 及启动门控，子进程在进入所属 Job 后才启动服务，包含 Python venv 的子进程。监督进程退出时 Job 会关闭。POSIX 使用独立进程组。
- `stop` 通过只绑定本机、随机令牌认证的控制端点请求监督进程关闭其拥有的进程；不会按端口、进程名或过期 PID 杀进程。失效状态只报告没有可连接的托管服务。
- 保留 [README](../README.md) 的双终端手动启动方式。手动启动的服务请在自己的终端停止；本入口不会接管它们。

默认输出可读诊断；加 `--json` 输出结构化 JSON。退出码 `0` 表示操作完成或诊断没有 error；`1` 表示操作失败/至少一项 error；参数无效为 `2`。服务未启动、端口占用、旧库待升级是 warning，缺失新库是 pending，所以诊断退出 `0` 不代表所有服务正在运行。

诊断参数要与启动参数一致，否则可能在检查另一个数据库或端口。`scope` 区分 `configured` 和 `isolated_demo`；与托管实例不一致时会提示。即使健康检查通过，也不会把未知端口占用者收归管理。

## 诊断内容与故障处理

| 检查 | 含义与处理 |
| --- | --- |
| Python / 后端依赖 | 检查 `.venv`、Python 3.11+ 和所需模块；缺失时在 backend 执行 `uv sync --frozen --extra dev`，或按 README 用 venv 与 requirements.lock 安装 |
| Node / 前端依赖 | 检查 Node.js 22+、Vite/Vue/插件可加载；缺失时安装 Node，并在 frontend 执行 `npm ci` |
| 端口已占用 | 可能是当前正常服务或其他程序；核对已启动实例，或选新端口，不自动终止占用者 |
| 服务未启动或不可连通 | 运行 start；核对后端、前端和代理端口；已有手动服务在其终端查看错误 |
| demo 模式 | 正常，无需密钥；体验评价只做结构检查 |
| AI 配置错误 | 在服务端检查 AI_PROVIDER、AI_BASE_URL、AI_MODEL、AI_API_KEY；诊断不发送模型请求 |
| 数据库不存在/为空 | 待初始化，诊断不会创建文件、目录、表或迁移记录；正式启动才会初始化 |
| 已识别旧版本 | 先备份再启动升级；不会在诊断时升级或登记版本 |
| 版本未知、结构不兼容或无法读取 | 保留原库，检查权限/配置，按数据管理说明校验备份，必要时使用匹配版本应用；不要改版本表 |
| 数据库正在变化 | 诊断可能拒绝不稳定的文件副本；稍后重试或停止学习服务后检查，不将不稳定副本当作健康库 |
| 托管启动失败/运行中退出 | 查看 `.cache/local/events.log` 的阶段说明，再运行相同参数的 diagnose；解决后重新 start |

SQLite 诊断把数据库、WAL 和回滚日志复制到临时目录，在副本上打开只读连接并核对已知完整结构；源文件和共享内存不会被 SQLite 打开，不会创建源端侧文件。复制期间源文件发生变化则拒绝该结果，不使用忽略 WAL 的 immutable 快捷方式。临时副本包含学习数据，检查结束自动清理；大库需要相应的本机临时空间。诊断不是可恢复备份，应继续使用专门的 backup 命令。

PostgreSQL 使用只读事务及超时检查。本轮未启动容器，PostgreSQL/Redis 实际运行仍未验证。

设置页的“运行状态”提供当前后端、模式和数据库状态，可用键盘刷新并展开处理指引。连接失败会移除旧的正常状态，给出终端诊断入口。前端依赖与离线端口检查需要本地命令完成；页面加载并不代表模型可连通。

诊断、设置和事件日志只输出允许的字段；不返回密钥、数据库/模型连接串、原始错误或学习内容。`.cache/local/state.json` 保存本机控制令牌，请勿分享；日志只记录阶段与明确错误，原始子进程输出不会持久保存。若 diagnose 全部正常但仍无法启动，可在完成备份后使用 README 的手动启动方式，在自己的终端定位启动错误，分享前先检查日志内容。
