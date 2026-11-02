"""Lost responses and concurrent retries must not duplicate learning evidence."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import importlib
import json
from threading import Event

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.datastructures import UploadFile

from app.idempotency import Claim, DEFER_COMMIT, RequestReceipt, ReceiptError, acquire, finish, utc_now
from app.models import Goal, KnowledgeEntry, LearningSession
from test_api import api as api, create_goal, make_due


def headers(key="request-12345678"):
    return {"Idempotency-Key": key}


def count(application, model):
    with application.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_goal_replay_survives_restart_and_json_formatting(api, monkeypatch):
    client, application, module = api
    calls = []
    original = module.generate_plan

    async def tracked(*args):
        calls.append(args)
        return await original(*args)

    monkeypatch.setattr(module, "generate_plan", tracked)
    body = {"title": "学习 Python 函数", "daily_minutes": 30}
    first = client.post("/api/goals", json=body, headers=headers())
    assert first.status_code == 201
    assert first.headers["Idempotency-Replayed"] == "false"
    reopened = module.create_app(str(application.state.engine.url))
    with TestClient(reopened) as other:
        replay = other.post("/api/goals", content=json.dumps(dict(reversed(list(body.items()))), indent=2),
                            headers={**headers(), "Content-Type": "application/json"})
    assert replay.status_code == 201 and replay.json() == first.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert len(calls) == 1
    assert count(application, Goal) == 1
    assert count(application, RequestReceipt) == 1


def test_key_cannot_change_path_or_payload(api):
    client, application, _ = api
    body = {"title": "第一份笔记", "content": "函数通过参数获取输入，使用返回值提供输出。"}
    assert client.post("/api/knowledge", json=body, headers=headers()).status_code == 201
    for path, changed in [("/api/knowledge", {**body, "title": "不同笔记"}), ("/api/goals", {"title": "学习 Python"})]:
        conflict = client.post(path, json=changed, headers=headers())
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_conflict"
    assert count(application, KnowledgeEntry) == 1
    assert count(application, Goal) == 0


def test_learn_and_failed_practice_replay_with_full_unit(api):
    client, application, _ = api
    unit = create_goal(client)["units"][0]["id"]
    path = f"/api/units/{unit}"
    body = {"reflection": "我理解函数接收参数作为输入，再通过返回值提供可以复用的输出结果。"}
    first = client.post(path + "/learn", json=body, headers=headers("learn-request-1"))
    assert first.status_code == 200
    assert first.json()["unit"]["stage"] == "practice"
    assert first.json()["unit"]["sessions"][0]["kind"] == "learn"
    assert "correct_index" not in first.json()["unit"]["practice"]
    assert client.post(path + "/learn", json=body, headers=headers("learn-request-1")).json() == first.json()
    bad = client.post(path + "/practice", json={"answer": "0"}, headers=headers("practice-request-1"))
    assert bad.status_code == 200 and bad.json()["passed"] is False
    assert client.post(path + "/practice", json={"answer": "0"}, headers=headers("practice-request-1")).json() == bad.json()
    assert count(application, LearningSession) == 2
    # A deliberate second attempt uses another key and remains a separate record.
    assert client.post(path + "/practice", json={"answer": "0"}, headers=headers("practice-request-2")).status_code == 200
    assert count(application, LearningSession) == 3


def test_chat_replay_does_not_repeat_provider_call(api, monkeypatch):
    client, application, module = api
    unit = create_goal(client)["units"][0]["id"]
    calls = []

    async def tracked(*args):
        calls.append(args)
        return {"reply": "用一个输入和输出例子检查自己的理解。", "mode": "demo"}

    monkeypatch.setattr(module, "tutor_reply", tracked)
    path = f"/api/units/{unit}/chat"
    first = client.post(path, json={"message": "返回值有什么作用？"}, headers=headers())
    again = client.post(path, json={"message": "返回值有什么作用？"}, headers=headers())
    assert again.json() == first.json() and again.status_code == 200
    assert len(calls) == 1 and count(application, LearningSession) == 1


def test_entire_learning_cycle_replays_assessments_and_reflection_once(api, monkeypatch):
    client, application, module = api
    unit = create_goal(client)["units"][0]["id"]
    path = f"/api/units/{unit}"
    calls = []
    original = module.evaluate_submission

    async def tracked(*args):
        calls.append(args[0])
        return await original(*args)

    monkeypatch.setattr(module, "evaluate_submission", tracked)

    def submit_and_replay(stage, body, key):
        first = client.post(f"{path}/{stage}", json=body, headers=headers(key))
        assert first.status_code == 200, first.text
        repeated = client.post(f"{path}/{stage}", json=body, headers=headers(key))
        assert repeated.status_code == 200 and repeated.json() == first.json()
        return first.json()

    submit_and_replay("learn", {"reflection": "我理解函数接收输入并用返回值提供结果，打印只是显示，需要结合例子验证。"}, "cycle-learn")
    submit_and_replay("practice", {"answer": "1"}, "cycle-practice")
    failed = submit_and_replay("project", {"content": "我尝试写了一个函数，但是还没有给出输入输出与边界条件的检查结果。"}, "cycle-project-bad")
    assert failed["passed"] is False
    content = "充分证据：我实现了 double 函数，将输入 3 变成结果 6，并测试输入 0 和负数的边界。"
    submit_and_replay("project", {"content": content}, "cycle-project-good")
    submit_and_replay("teach", {"content": content}, "cycle-teach")
    submit_and_replay("reflect", {
        "content": "通过实践发现，理解函数必须区别返回值和打印，这改变了我原来模糊的认识。",
        "takeaway": "函数的输入输出可以用实例逐一验证。",
        "change": "我以前只关注显示结果，现在更关注可复用的返回值。",
    }, "cycle-reflect")
    assert count(application, KnowledgeEntry) == 1
    make_due(application, unit)
    result = submit_and_replay("review", {"rating": 3, "answer": content}, "cycle-review")
    assert result["unit"]["stage"] == "complete" and result["unit"]["review_count"] == 1
    assert count(application, LearningSession) == 7
    assert calls == ["project", "project", "teach", "review"]


def test_import_replay_ignores_multipart_boundary_and_normalizes_filename(api):
    client, application, _ = api
    content = "# 函数\n通过输入、返回值与边界条件验证函数。".encode()
    first = client.post("/api/knowledge/import", files={"file": ("../../函数.md", content, "text/markdown")}, headers=headers())
    second = client.post("/api/knowledge/import", files={"file": ("函数.md", content, "text/markdown")}, headers=headers())
    assert first.status_code == 201, first.text
    assert second.status_code == 201 and second.json() == first.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    assert count(application, KnowledgeEntry) == 1
    changed = client.post("/api/knowledge/import", files={"file": ("函数.md", content + b"changed", "text/markdown")}, headers=headers())
    assert changed.status_code == 409


def test_upload_files_close_on_replay_conflict_and_early_error(api, monkeypatch):
    client, _, _ = api
    files = []
    original = UploadFile.read

    async def track_read(file, size=-1):
        if file not in files:
            files.append(file)
        return await original(file, size)

    monkeypatch.setattr(UploadFile, "read", track_read)
    content = b"# a note with enough learning material"
    for value, expected in [(content, 201), (content, 201), (content + b"changed", 409), (b"x" * (10 * 1024 * 1024 + 1), 413)]:
        response = client.post("/api/knowledge/import", files={"file": ("note.md", value, "text/markdown")}, headers=headers())
        assert response.status_code == expected
        assert files and all(file.file.closed for file in files)


def test_validation_and_provider_failure_release_claim_for_retry(api, monkeypatch):
    client, application, module = api
    assert client.post("/api/goals", json={"title": "x"}, headers=headers()).status_code == 422
    assert count(application, RequestReceipt) == 0
    original = module.generate_plan

    async def unavailable(*_):
        raise module.ProviderError("暂时无法连接模型服务。")

    monkeypatch.setattr(module, "generate_plan", unavailable)
    body = {"title": "学习 Python"}
    assert client.post("/api/goals", json=body, headers=headers()).status_code == 502
    assert count(application, Goal) == 0 and count(application, RequestReceipt) == 0
    monkeypatch.setattr(module, "generate_plan", original)
    assert client.post("/api/goals", json=body, headers=headers()).status_code == 201
    assert count(application, Goal) == 1


def test_concurrent_requests_across_app_instances_claim_only_once(api, monkeypatch):
    client, application, module = api
    started, proceed = Event(), Event()
    calls = []
    original = module.generate_plan

    async def delayed(*args):
        calls.append(args)
        started.set()
        assert await asyncio.to_thread(proceed.wait, 5)
        return await original(*args)

    monkeypatch.setattr(module, "generate_plan", delayed)
    other_app = module.create_app(str(application.state.engine.url))
    body = {"title": "学习 Python"}
    with TestClient(other_app) as other, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, "/api/goals", json=body, headers=headers())
        try:
            assert started.wait(5)
            competing = other.post("/api/goals", json=body, headers=headers())
            assert competing.status_code == 409
            assert competing.json()["code"] == "idempotency_in_progress"
            assert competing.headers["Retry-After"] == "2"
        finally:
            proceed.set()
        completed = future.result(5)
        replay = other.post("/api/goals", json=body, headers=headers())
    assert completed.status_code == 201 and replay.json() == completed.json()
    assert len(calls) == 1 and count(application, Goal) == 1


def test_receipt_commit_failure_rolls_back_business_data(api, monkeypatch):
    client, application, _ = api
    original = Session.commit

    def fail_business_commit(db):
        if db.info.get(DEFER_COMMIT):
            raise RuntimeError("simulated database failure after business flush")
        return original(db)

    monkeypatch.setattr(Session, "commit", fail_business_commit)
    body = {"title": "学习 Python"}
    with pytest.raises(RuntimeError, match="simulated database failure"):
        client.post("/api/goals", json=body, headers=headers())
    assert count(application, Goal) == 0
    assert count(application, RequestReceipt) == 0
    monkeypatch.setattr(Session, "commit", original)
    assert client.post("/api/goals", json=body, headers=headers()).status_code == 201
    assert count(application, Goal) == 1 and count(application, RequestReceipt) == 1


def test_expired_owner_cannot_commit_business_or_receipt(api):
    _, application, _ = api
    factory = application.state.session_factory
    old = acquire(factory, "lease-request-1", "a" * 64)
    assert isinstance(old, Claim)
    with factory() as db:
        db.get(RequestReceipt, old.key).lease_until = utc_now() - timedelta(seconds=1)
        db.commit()
    new = acquire(factory, old.key, "a" * 64)
    assert isinstance(new, Claim) and new.owner_token != old.owner_token
    with factory() as db:
        db.add(KnowledgeEntry(title="旧请求不应保存", content="该事务已经失去请求所有权。", source="note"))
        db.flush()
        with pytest.raises(ReceiptError) as error:
            finish(db, old, JSONResponse({"saved": "old"}))
        assert error.value.code == "idempotency_expired_owner"
        db.rollback()
    assert count(application, KnowledgeEntry) == 0
    with factory() as db:
        db.add(KnowledgeEntry(title="恢复后的请求", content="新的所有者可以提交实际数据。", source="note"))
        db.flush()
        finish(db, new, JSONResponse({"saved": "new"}))
    replay = acquire(factory, old.key, "a" * 64)
    assert json.loads(replay.body) == {"saved": "new"}
    assert count(application, KnowledgeEntry) == 1


def test_claim_cleanup_after_route_failure_does_not_remove_other_owner(api, monkeypatch):
    client, application, module = api
    receipts = importlib.import_module("app.idempotency")
    original = module.generate_plan

    async def stolen(*args):
        with application.state.session_factory() as db:
            receipt = db.get(RequestReceipt, "request-12345678")
            receipt.owner_token = "another-owner"
            db.commit()
        return await original(*args)

    monkeypatch.setattr(module, "generate_plan", stolen)
    response = client.post("/api/goals", json={"title": "学习 Python"}, headers=headers())
    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_expired_owner"
    assert count(application, Goal) == 0
    with application.state.session_factory() as db:
        receipt = db.get(receipts.RequestReceipt, "request-12345678")
        assert receipt.status == "pending" and receipt.owner_token == "another-owner"


def test_key_validation_and_cors(api):
    client, application, _ = api
    response = client.post("/api/goals", json={"title": "学习 Python"}, headers=headers("bad key"))
    assert response.status_code == 422
    assert count(application, RequestReceipt) == 0
    preflight = client.options("/api/goals", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type, Idempotency-Key",
    })
    assert preflight.status_code == 200
    written = client.post("/api/goals", json={"title": "学习 Python"}, headers={**headers(), "Origin": "http://localhost:5173"})
    assert "Idempotency-Replayed" in written.headers["Access-Control-Expose-Headers"]


def test_deleting_note_erases_receipt_content_and_prevents_recreation(api):
    client, application, _ = api
    body = {"title": "要删除的个人笔记", "content": "这段个人学习笔记不应在删除后继续藏在提交回执里。"}
    first = client.post("/api/knowledge", json=body, headers=headers())
    assert first.status_code == 201
    assert client.delete(f"/api/knowledge/{first.json()['id']}").status_code == 204
    with application.state.session_factory() as db:
        receipt = db.get(RequestReceipt, "request-12345678")
        assert receipt.status == "deleted" and receipt.response_body is None
    replay = client.post("/api/knowledge", json=body, headers=headers())
    assert replay.status_code == 410 and replay.json()["code"] == "idempotency_resource_deleted"
    assert body["content"] not in replay.text
    assert count(application, KnowledgeEntry) == 0


def test_goal_deletion_erases_goal_and_chat_receipts_but_keeps_other_note(api):
    client, application, _ = api
    body = {"title": "要删除的学习目标"}
    goal = client.post("/api/goals", json=body, headers=headers("delete-goal-key"))
    assert goal.status_code == 201
    unit = goal.json()["units"][0]["id"]
    path = f"/api/units/{unit}/chat"
    chat_body = {"message": "这条导师对话应与学习目标一起删除。"}
    assert client.post(path, json=chat_body, headers=headers("delete-chat-key")).status_code == 200
    separate = {"title": "独立保留的笔记", "content": "这份独立笔记与被删除的学习目标并没有关联。"}
    assert client.post("/api/knowledge", json=separate, headers=headers("keep-note-key")).status_code == 201
    assert client.delete(f"/api/goals/{goal.json()['id']}").status_code == 204
    for retry_path, retry_body, key in [("/api/goals", body, "delete-goal-key"), (path, chat_body, "delete-chat-key")]:
        replay = client.post(retry_path, json=retry_body, headers=headers(key))
        assert replay.status_code == 410 and replay.json()["code"] == "idempotency_resource_deleted"
    with application.state.session_factory() as db:
        tombstones = db.scalars(select(RequestReceipt).where(RequestReceipt.status == "deleted")).all()
        assert len(tombstones) == 2 and all(item.response_body is None for item in tombstones)
        assert db.get(RequestReceipt, "keep-note-key").status == "complete"
    assert count(application, Goal) == 0 and count(application, LearningSession) == 0
    assert count(application, KnowledgeEntry) == 1
