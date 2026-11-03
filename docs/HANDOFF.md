# DoKnow 开发交接

更新日期：2026-11-03（Asia/Shanghai）。恢复时先核对实际 Git 状态，再读 [进度记录](PROGRESS.md)。

## 当前轮：P1-3 课程调整与证据保留

从 `97e45b8bcc9124874ed9b43ad7e6c075611dbdaa` 的干净 develop 开始，基线自己的 CI 41586788188 五项成功已核对。原会话在只读代码阶段中断，本轮恢复后完成实现，最终验证和提交状态见 PROGRESS.md 顶部。

- 重生成、难度调整和单元重排均先保存预览，再由用户明确确认；独立 `course_version`，不改变目标基础编辑的版本语义。
- 有已保存聊天、学习提交、进度、关联笔记或复习记录的单元固定保留。只替换/重排未开始槽位，保留原课程数量。替换使用新 ID，旧单元材料归档为只读；草稿仍保留在旧 ID。
- 预览绑定目标基础版本、课程版本和全部活动单元版本。预览后学习/编辑/调整会使确认失败，要求重新预览。模型等待期间不持有写锁；确认、归档、新单元、历史和幂等回执同事务保存。
- 预览/确认支持丢响应与重启后原操作恢复；历史 API 不包含答案或题库。删除目标清理课程历史及回执正文，独立笔记保留。
- 学习页和概览有调整入口，变更记录可打开旧材料；支持键盘、焦点恢复、手机预览及已保存但同步失败的提示。

完整规则：[COURSE_ADJUSTMENTS.md](COURSE_ADJUSTMENTS.md)。API：[API_CONTRACT.md](API_CONTRACT.md)。运行与备份：[LOCAL_RUNNING.md](LOCAL_RUNNING.md)、[DATA_MANAGEMENT.md](DATA_MANAGEMENT.md)。

## 仓库与数据

- 实际仓库：`D:\Project\learn-agent\DoKnow`。父目录有另一个空 Git 仓库，不要在父目录提交。
- 分支 develop；origin 为 BennyZ359/DoKnow。普通推送，不强推、不重写历史、不向 main 发布。每次 Git 写入前核对目录、分支和暂存差异，按具体文件暂存。
- 后端环境 `backend/.venv`。应用版本现为 `0005_course_changes`；仅独立测试库已迁移，正式学习库未升级。新版本启动正式库会迁移，使用前备份；diagnose 保持只读。
- 使用 demo、模拟模型与独立数据库；不调用付费模型、不启动 Docker。真实模型和 PostgreSQL/Redis 容器仍未实测。
- `.env`、`backend/data/`、备份、`.cache/`、依赖和浏览器产物不提交。已有授权应沿用；若推送被平台拒绝，记录明确理由，不绕过审批。

## 实现入口

1. `backend/app/courses.py`：保留规则、预览快照、条件更新、应用与历史序列化。
2. `backend/app/main.py`：course 读取/预览/确认、归档写入保护；`idempotency.py`：课程回执与删除范围。
3. `backend/app/models.py`、`migrations/versions/0005_course_changes.py`：课程版本、归档和变更表；旧版 schema 保持冻结。
4. `backend/app/services/learning.py`：只重生成未开始部分，保留主题上下文，demo 模板及 AI 响应校验。
5. `frontend/src/components/CourseEditor.vue`：课程界面；`App.vue`：入口、归档状态及删除清理；`writes.ts`：恢复记录格式。
6. `backend/tests/test_courses.py`、`test_migrations.py`、`test_services.py` 与 `tests/browser/courses.spec.ts`：数据、竞争、恢复、迁移、模型上下文和界面回归。

## 验证与收尾

backend：`.venv/Scripts/python -m pytest -q`；`.venv/Scripts/ruff check app tests ../scripts`。

frontend：`npm run build`、`npm run format:check`。tests/browser：`npm test`，同一时间仅一个 runner，使用独立 SQLite 和 8001/5174 端口。Windows Playwright 用例结束后仍可能等待 webServer 收尾；依据本次日志、PID、父子关系和完整命令核对，只停止本轮启动的测试服务，取得最终退出码。不按端口批量结束进程。

根目录：`docker --config .cache/docker compose config --quiet`（仅静态）、`git diff --check` 和 Markdown 本地链接。手机截图 `.cache/browser/course-preview-mobile.png` 已人工查看，不提交。

完成后用实际最终 HEAD 查询其自身 CI，不能拿基线成功替代。下一轮 P1-5 真实模型少量联调或 P1-7 实际容器验证须根据用户配置与范围安排；不重复开发本轮课程调整。
