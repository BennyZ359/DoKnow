"""Edits retain evidence, reject stale pages, and recover committed saves."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.idempotency import RequestReceipt
from app.models import Goal, KnowledgeEntry
from test_api import api as api, complete_until_review, create_goal


def note(client, **fields):
    response = client.post("/api/knowledge", json={
        "title": "函数学习笔记", "content": "原始认识：通过输入和输出理解函数。", **fields,
    })
    assert response.status_code == 201, response.text
    return response.json()


def resource(client, kind):
    item = create_goal(client) if kind == "goals" else note(client)
    return f"/api/{kind}/{item['id']}", item


def test_goal_edit_keeps_every_course_and_learning_value(api, monkeypatch):
    client, application, module = api
    goal = create_goal(client)
    complete_until_review(client, goal["units"][0]["id"])

    def snapshot():
        with application.state.engine.connect() as db:
            return {name: db.exec_driver_sql(f"SELECT * FROM {name} ORDER BY id").all()
                    for name in ("units", "learning_sessions", "knowledge_entries")}

    before = snapshot()

    async def forbidden(*_):
        pytest.fail("Editing basic information must not regenerate or evaluate a course")

    monkeypatch.setattr(module, "generate_plan", forbidden)
    monkeypatch.setattr(module, "evaluate_submission", forbidden)
    response = client.patch(f"/api/goals/{goal['id']}", json={
        "version": goal["version"], "title": "函数与可复用计算", "motivation": "", "daily_minutes": 60,
    })
    assert response.status_code == 200, response.text
    saved = response.json()
    assert (saved["title"], saved["motivation"], saved["daily_minutes"], saved["version"]) == ("函数与可复用计算", "", 60, 2)
    assert saved["created_at"] == goal["created_at"] and saved["updated_at"] >= goal["updated_at"]
    assert saved["progress"] == 30 and saved["level"] == goal["level"]
    assert snapshot() == before
    unit = client.get(f"/api/units/{goal['units'][0]['id']}").json()
    assert unit["goal_title"] == saved["title"]
    assert len(unit["sessions"]) == 5 and unit["stage"] == "review"


def test_reflection_original_survives_edits_and_goal_deletion(api):
    client, application, _ = api
    goal = create_goal(client)
    complete_until_review(client, goal["units"][0]["id"])
    original = client.get("/api/knowledge").json()[0]
    path = f"/api/knowledge/{original['id']}"
    unit_path = f"/api/units/{goal['units'][0]['id']}"
    evidence = client.get(unit_path).json()["sessions"]
    first = client.patch(path, json={"version": 1, "title": "重新理解函数", "content": "更新认识：返回值可以参与下一步计算。",
                                     "tags": [" Python ", "python", "复盘"]})
    assert first.status_code == 200, first.text
    assert first.json()["tags"] == ["Python", "复盘"]
    assert first.json()["original"] == {"title": original["title"], "content": original["content"]}
    assert client.patch(path, json={"version": 2, "content": "再次整理：通过独立检验理解函数的边界。"}).status_code == 200
    assert client.get(unit_path).json()["sessions"] == evidence
    assert client.delete(f"/api/goals/{goal['id']}").status_code == 204
    saved = client.get(path).json()
    assert saved["source"] == "reflection" and saved["version"] == 3
    assert saved["original"] == first.json()["original"]
    assert saved["created_at"] == original["created_at"]
    with application.state.session_factory() as db:
        assert db.get(KnowledgeEntry, original["id"]).unit_id is None
    exported = client.get(path + "/export")
    assert "再次整理" in exported.text and original["content"] in exported.text


@pytest.mark.parametrize("fields", [
    {"version": True, "title": "有效标题"}, {"version": 0, "title": "有效标题"},
    {"title": "缺少版本"}, {"version": 1}, {"version": 1, "title": None},
    {"version": 1, "level": "advanced"}, {"version": 1, "units": []},
    {"version": 1, "daily_minutes": "30"}, {"version": 1, "daily_minutes": 181},
])
def test_goal_edit_rejects_unsupported_or_invalid_changes(api, fields):
    client, _, _ = api
    path, original = resource(client, "goals")
    response = client.patch(path, json=fields)
    assert response.status_code == 422, response.text
    assert client.get(path).json() == original


@pytest.mark.parametrize("fields", [
    {"tags": ["bad\x00tag"]}, {"tags": ["bad\ud800tag"]}, {"tags": ["line\nbreak"]},
    {"tags": [" "]}, {"tags": ["x" * 41]}, {"tags": [f"tag{i}" for i in range(21)]},
    {"tags": "not an array"}, {"content": " " * 20}, {"source": "reflection"},
    {"original": {"title": "伪造证据", "content": "伪造证据"}}, {"tags": None},
])
def test_note_edit_rejects_invalid_tags_and_evidence_changes(api, fields):
    client, _, _ = api
    path, original = resource(client, "knowledge")
    response = client.patch(path, content=json.dumps({"version": 1, **fields}), headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert "input" not in response.json()["detail"][0]
    assert client.get(path).json()["version"] == original["version"]


def test_search_filters_and_markdown_exports_current_and_original(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv("AI_API_KEY", "export-must-not-contain-this-secret")
    first = note(client, tags=["Python", "复盘"])
    note(client, title="写作笔记", content="通过例子说明结构，修改以后重新阅读。", tags=["写作"])
    imported = client.post("/api/knowledge/import", files={"file": ("../../参考资料.md", "参考资料包含函数的新认识。".encode())}).json()
    assert [item["id"] for item in client.get("/api/knowledge", params={"q": "python", "tag": "PYTHON", "source": "note"}).json()] == [first["id"]]
    assert client.get("/api/knowledge", params={"tag": "py"}).json() == []
    assert [item["id"] for item in client.get("/api/knowledge", params={"source": "import"}).json()] == [imported["id"]]
    assert client.get("/api/knowledge", params={"q": "%_"}).json() == []
    body = "## 更新后的函数\n\n```python\ndef double(x):\n    return x * 2\n```\n\n中文正文与 Markdown 保留。"
    assert client.patch(f"/api/knowledge/{first['id']}", json={"version": 1, "title": "新版函数笔记", "content": body}).status_code == 200
    exported = client.get("/api/knowledge/export", params={"tag": "Python", "q": "新版"})
    assert exported.status_code == 200 and exported.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in exported.headers["content-disposition"]
    assert body in exported.text and first["content"] in exported.text
    assert "写作笔记" not in exported.text and "export-must-not-contain-this-secret" not in exported.text
    assert "原始记录（保留）" in exported.text and "Python, 复盘" in exported.text
    assert client.get("/api/knowledge/missing/export").status_code == 404


@pytest.mark.parametrize("kind", ["goals", "knowledge"])
@pytest.mark.parametrize("with_key", [False, True])
def test_two_concurrent_editors_cannot_silently_overwrite(api, monkeypatch, kind, with_key):
    client, application, module = api
    path, original = resource(client, kind)
    barrier = Barrier(2)
    require_version = module.require_version

    def both_read(item, version):
        require_version(item, version)
        barrier.wait(timeout=10)

    monkeypatch.setattr(module, "require_version", both_read)
    other_app = module.create_app(str(application.state.engine.url))
    with TestClient(other_app) as other, ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(peer.patch, path, json={"version": original["version"], "title": f"页面 {index} 的修改"},
                             headers={"Idempotency-Key": f"editor-{index}-12345"} if with_key else {})
                 for index, peer in enumerate((client, other))]
        results = [task.result(15) for task in tasks]
    assert sorted(result.status_code for result in results) == [200, 409], [result.text for result in results]
    failed = next(result for result in results if result.status_code == 409)
    assert failed.json()["code"] == "edit_conflict"
    winner = next(result for result in results if result.status_code == 200).json()
    current = client.get(path).json()
    assert current["version"] == 2 and current["title"] == winner["title"]


@pytest.mark.parametrize("kind", ["goals", "knowledge"])
def test_edit_receipt_replay_after_restart_and_later_edit_then_delete(api, kind):
    client, application, module = api
    path, _ = resource(client, kind)
    key = {"Idempotency-Key": "lost-edit-response"}
    payload = {"version": 1, "title": "第一次保存的标题"}
    first = client.patch(path, json=payload, headers=key)
    assert first.status_code == 200, first.text
    assert client.patch(path, json={"version": 2, "title": "后续页面修改的标题"}).status_code == 200
    restarted = module.create_app(str(application.state.engine.url))
    with TestClient(restarted) as other:
        replay = other.patch(path, json=payload, headers=key)
        assert replay.status_code == 200 and replay.json() == first.json()
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert other.get(path).json()["title"] == "后续页面修改的标题"
        conflict = other.patch(path, json={**payload, "title": "不同内容复用标识"}, headers=key)
        assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
        stale = other.patch(path, json=payload)
        assert stale.status_code == 409 and stale.json()["code"] == "edit_conflict"
        assert other.delete(path).status_code == 204
        erased = other.patch(path, json=payload, headers=key)
        assert erased.status_code == 410 and erased.json()["code"] == "idempotency_resource_deleted"
    with application.state.session_factory() as db:
        receipt = db.get(RequestReceipt, key["Idempotency-Key"])
        assert receipt.status == "deleted" and receipt.response_body is None


def test_failed_edit_commit_rolls_back_snapshot_and_allows_retry(api, monkeypatch):
    client, application, _ = api
    from app import idempotency
    path, original = resource(client, "knowledge")
    finish = idempotency.finish

    def fail(*args):
        raise RuntimeError("simulated edit commit failure")

    monkeypatch.setattr(idempotency, "finish", fail)
    payload = {"version": 1, "content": "修改后的正文，只在成功提交后才能保存。"}
    key = {"Idempotency-Key": "atomic-edit-save"}
    with pytest.raises(RuntimeError, match="simulated"):
        client.patch(path, json=payload, headers=key)
    with application.state.session_factory() as db:
        item = db.get(KnowledgeEntry, original["id"])
        assert item.content == original["content"] and item.original is None and item.version == 1
        assert db.scalar(select(RequestReceipt)) is None
    monkeypatch.setattr(idempotency, "finish", finish)
    assert client.patch(path, json=payload, headers=key).status_code == 200


@pytest.mark.parametrize("kind", ["goals", "knowledge"])
def test_identical_save_consumes_version_even_when_clock_does_not_advance(api, monkeypatch, kind):
    client, application, module = api
    path, original = resource(client, kind)
    # Repeated saves need a reliable concurrency token even with a coarse clock.
    with application.state.session_factory() as db:
        unchanged_time = db.get(Goal if kind == "goals" else KnowledgeEntry, original["id"]).updated_at
    monkeypatch.setattr(module, "now_utc", lambda: unchanged_time)
    for version in (1, 2):
        response = client.patch(path, json={"version": version, "title": original["title"]})
        assert response.status_code == 200, response.text
        assert response.json()["version"] == version + 1
    assert client.patch(path, json={"version": 2, "title": "过期页面的修改"}).status_code == 409


def test_qa_cache_uses_updated_title_body_and_revision(api, monkeypatch):
    client, _, module = api
    cached, calls = {}, []

    async def get_cache(self, key):
        return cached.get(key)

    async def put_cache(self, key, result):
        cached[key] = result

    async def answer(question, documents):
        calls.append(documents)
        return {"answer": "\n".join(item["content"] for item in documents), "mode": "demo",
                "sources": [{"id": item["id"], "title": item["title"], "excerpt": item["content"]} for item in documents]}

    monkeypatch.setattr(module.AnswerCache, "get", get_cache)
    monkeypatch.setattr(module.AnswerCache, "put", put_cache)
    monkeypatch.setattr(module, "answer_question", answer)
    item = note(client)
    path = f"/api/knowledge/{item['id']}"
    query = {"question": "函数是什么？"}
    assert item["content"] in client.post("/api/knowledge/ask", json=query).text
    client.post("/api/knowledge/ask", json=query)
    assert len(calls) == 1
    client.patch(path, json={"version": 1, "title": "新版认识", "content": "新版正文：通过返回值组合计算，边界条件必须检查。"})
    current = client.post("/api/knowledge/ask", json=query)
    assert "新版正文" in current.text and "新版认识" in current.text and item["content"] not in current.text
    assert len(calls) == 2 and all("original" not in document for document in calls[-1])
    client.patch(path, json={"version": 2, "tags": ["复盘"]})
    client.post("/api/knowledge/ask", json=query)
    assert len(calls) == 3
    client.delete(path)
    assert client.post("/api/knowledge/ask", json=query).json()["sources"] == []


def test_inflight_answer_is_rejected_when_materials_change(api, monkeypatch):
    client, application, module = api
    item = note(client)
    started, proceed = Event(), Event()

    async def delayed(question, documents):
        started.set()
        assert await asyncio.to_thread(proceed.wait, 10)
        return {"answer": documents[0]["content"], "sources": [], "mode": "demo"}

    monkeypatch.setattr(module, "answer_question", delayed)
    other_app = module.create_app(str(application.state.engine.url))
    with TestClient(other_app) as other, ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(client.post, "/api/knowledge/ask", json={"question": "解释函数"})
        try:
            assert started.wait(10)
            assert other.patch(f"/api/knowledge/{item['id']}", json={"version": 1, "content": "最新认识：使用输入输出验证函数边界。"}).status_code == 200
        finally:
            proceed.set()
        result = task.result(10)
    assert result.status_code == 409 and result.json()["code"] == "knowledge_changed"


def test_backup_restores_edited_notes_goals_and_save_receipts(api, tmp_path):
    client, application, module = api
    from app.data import backup_database, restore_database
    from app.migrations import CURRENT
    goal_path, _ = resource(client, "goals")
    note_path, _ = resource(client, "knowledge")
    payload = {"version": 1, "title": "备份中的编辑标题", "tags": ["待复习"]}
    key = {"Idempotency-Key": "backup-edit-receipt"}
    saved_note = client.patch(note_path, json=payload, headers=key).json()
    saved_goal = client.patch(goal_path, json={"version": 1, "daily_minutes": 75}).json()
    backup = tmp_path / "edit-backup.db"
    assert backup_database(str(application.state.engine.url), backup)["revision"] == CURRENT
    client.patch(note_path, json={"version": 2, "title": "备份之后的新修改"})
    restored_url = f"sqlite:///{tmp_path / 'restored-edits.db'}"
    restore_database(backup, restored_url)
    restored = module.create_app(restored_url)
    with TestClient(restored) as other:
        assert other.get(note_path).json() == saved_note
        assert other.get(goal_path).json() == saved_goal
        replay = other.patch(note_path, json=payload, headers=key)
        assert replay.headers["Idempotency-Replayed"] == "true" and replay.json() == saved_note
    assert client.get(note_path).json()["title"] == "备份之后的新修改"
