# v0.1 验证记录

验证日期：2026-11-02（Asia/Shanghai）。验证对象为本次新增的本地首版。

| 检查 | 结果 | 覆盖与限制 |
| --- | --- | --- |
| 后端 pytest | 54 项通过 | 21 项 API、30 项智能/文档服务、3 项缓存测试 |
| Ruff | 通过 | 后端 app 与 tests |
| Vue / TypeScript 生产构建 | 通过 | vue-tsc 与 Vite 构建 |
| 前端依赖审计 | 0 vulnerabilities | 本次 npm audit 结果，不代表未来无漏洞 |
| 浏览器端到端 | 3 项通过 | Chrome、桌面 1440px 与手机 390px，真实前后端与独立 SQLite 数据库 |
| Compose 配置 | 通过 | docker compose config --quiet |
| Docker / PostgreSQL / Redis 实际容器运行 | 未验证 | 引擎未启动；用户选择先完成本地版本 |
| 真实在线模型 | 未调用 | 没有使用用户密钥；模型请求通过实际 httpx MockTransport 验证 |

## 真实浏览器流程

第一项从网页创建 Python 学习目标，向导师提问，记录理解，先提交错误选择再改正，提交购物程序与边界结果，完成给初学者的讲解，写下复盘、沉淀与认识变化。刷新页面后状态恢复；在**隔离的测试数据库**调整到期时间，再完成主动回忆并检查知识笔记。应用不提供绕过复习时间的接口。

第二项将导师回复延迟，在请求未结束时切换另一个学习单元，验证旧回复不会覆盖新单元。

第三项导入 Markdown，提出有材料支持和缺乏材料支持的两个问题，核对来源与不足提示，然后在手机尺寸打开导航，确认页面没有横向溢出。桌面与手机截图也经过人工视觉检查。

## 后端的关键验证

包括服务器阶段约束、正确与错误答案、重复与并发提交、模型故障不推进状态、复习未到期拒绝提交、自评不能覆盖回忆证据、遗忘后的间隔重置、应用重启恢复、删除目标保留独立沉淀、实际 PDF/DOCX 解析、文档限制、中英文检索、长笔记尾部检索与引用真实性。

模型边界验证实际请求 URL、鉴权头、结构化 JSON 格式、超时、限流、服务失败、重定向和无效计划不持久化。输入验证包括 NUL、无效 Unicode、NaN、文件名与大输入错误响应。Redis 缓存验证内容变化失效与缓存不可用时继续运行；不宣称实际 Redis 服务器已经运行验证。

## 复现

在后端安装开发依赖，并在前端安装依赖后：

```powershell
cd backend
uv sync --extra dev
uv run pytest -q
uv run ruff check app tests
```

```powershell
cd frontend
npm ci
npm run build
npm audit
```

浏览器测试需要 Chrome，或选择已安装的 Playwright Chromium：

```powershell
cd tests/browser
npm ci
npm test
```

默认自动启动端口 8001 的测试后端和端口 5174 的前端。请先确认两端口空闲。测试数据库随机创建于项目 `.cache/browser/`，不会写入正式 `backend/data/doknow.db`。Windows 环境需已安装 Chrome；Linux CI 使用 `DOKNOW_BROWSER_CHANNEL=chromium` 配合 `npx playwright install --with-deps chromium`。

## 尚未验证的部署

后台启动 Docker Desktop 的操作未获自动审批执行：审批代理返回 HTTP 400 content-blocked，实际提权操作没有执行。随后用户选择先交付本地版本，不再继续容器启动。Docker 配置静态检查通过，但镜像构建、PostgreSQL 与 Redis 联通不能据此视为已验证。

后续可在运行中的 Docker Engine 上执行 `docker compose up --build -d`，检查 `/api/health` 返回 PostgreSQL，再重复学习闭环与资料问答，最后验证重启后的数据恢复。首版仅面向本地个人使用，不含多用户访问控制。
