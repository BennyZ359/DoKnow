"""Course changes preserve evidence and remain safe across stale pages and retries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app import courses
from app.data import backup_database, restore_database
from app.idempotency import RequestReceipt
from app.models import CourseChange, Goal, Unit
from test_api import api as api, complete_until_review, create_goal, make_due


def path(goal):
    return f"/api/goals/{goal['id']}/course"


def preview(client, goal, kind="regenerate", **fields):
    response = client.post(path(goal) + "/preview", json={
        "course_version": goal["course_version"], "kind": kind, **fields,
    })
    assert response.status_code == 201, response.text
    return response.json()


def apply(client, goal, change, key="course-confirmation"):
    return client.post(path(goal) + "/apply", json={"preview_id": change["id"], "confirmed": True},
                       headers={"Idempotency-Key": key} if key else {})


@pytest.mark.parametrize("kind", ["regenerate", "difficulty"])
def test_replacement_preserves_complete_evidence_and_old_materials(api, kind):
    client, application, _ = api
    goal = create_goal(client)
    fixed = goal["units"][0]["id"]
    complete_until_review(client, fixed)
    make_due(application, fixed)
    review_payload = {"rating": 3, "answer": "充分证据：函数通过明确参数接收输入，返回值交付结果，零值和负数检验边界。"}
    receipt_headers = {"Idempotency-Key": "retained-review-evidence"}
    review = client.post(f"/api/units/{fixed}/review", json=review_payload, headers=receipt_headers)
    assert review.status_code == 200

    def evidence():
        with application.state.engine.connect() as db:
            return {
                "unit": db.exec_driver_sql("SELECT * FROM units WHERE id=?", (fixed,)).all(),
                **{name: db.exec_driver_sql(f"SELECT * FROM {name} ORDER BY id").all()
                   for name in ("learning_sessions", "knowledge_entries")},
                "receipt": db.exec_driver_sql("SELECT * FROM request_receipts WHERE key='retained-review-evidence'").all(),
            }

    before = evidence()
    old = client.get(f"/api/units/{goal['units'][1]['id']}").json()
    change = preview(client, goal, kind, **({"level": "advanced"} if kind == "difficulty" else {}))
    assert client.get(f"/api/goals/{goal['id']}").json()["course_version"] == 1
    assert change["before"]["units"][0]["retained"] is True
    assert "correct_index" not in str(change) and "practice_variants" not in str(change)
    assert evidence() == before
    result = apply(client, goal, change)
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["course_version"] == 2 and saved["version"] == goal["version"]
    assert saved["units"][0]["id"] == fixed and saved["progress"] == 33
    assert evidence() == before
    assert saved["level"] == ("advanced" if kind == "difficulty" else "beginner")
    assert len(saved["units"]) == 3
    assert saved["units"][1]["id"] != old["id"]
    archived = client.get(f"/api/units/{old['id']}").json()
    assert archived == {**old, "archived": True}
    assert client.post(f"/api/units/{old['id']}/chat", json={"message": "旧页面"}).status_code == 409
    assert client.post(f"/api/units/{old['id']}/learn", json={"reflection": "我理解了函数的输入和输出，需要用具体例子验证边界和返回值。"}).status_code == 409
    replay = client.post(f"/api/units/{fixed}/review", json=review_payload, headers=receipt_headers)
    assert replay.json() == review.json() and replay.headers["Idempotency-Replayed"] == "true"
    history = client.get(path(goal)).json()["history"]
    assert len(history) == 1 and history[0]["applied_at"]
    assert history[0]["before"] == change["before"] and history[0]["after"] == change["after"]
    # Metadata editors keep their version across course changes.
    metadata = client.patch(f"/api/goals/{goal['id']}", json={"version": 1, "daily_minutes": 50})
    assert metadata.status_code == 200 and metadata.json()["course_version"] == 2


def test_reorder_pins_chat_only_unit_and_preserves_ids_and_materials(api, monkeypatch):
    client, application, module = api
    goal = create_goal(client)
    ids = [unit["id"] for unit in goal["units"]]
    client.post(f"/api/units/{ids[1]}/chat", json={"message": "这还没有学习提交，但聊天也应保留。"})
    with application.state.session_factory() as db:
        materials = {unit.id: unit.material for unit in db.scalars(select(Unit))}
    async def forbidden(*args):
        pytest.fail("Reordering must not call a provider")
    monkeypatch.setattr(module, "regenerate_units", forbidden)
    change = preview(client, goal, "reorder", unit_ids=[ids[2], ids[0]])
    saved = apply(client, goal, change).json()
    assert [unit["id"] for unit in saved["units"]] == [ids[2], ids[1], ids[0]]
    assert saved["units"][1]["position"] == 1
    with application.state.session_factory() as db:
        assert {unit.id: unit.material for unit in db.scalars(select(Unit))} == materials
    assert client.get(f"/api/units/{ids[1]}").json()["sessions"][0]["content"].startswith("这还没有")


@pytest.mark.parametrize("mutation", ["learn", "chat", "metadata", "other_course", "delete"])
def test_changes_after_preview_are_rejected(api, mutation):
    client, _, _ = api
    goal = create_goal(client)
    change = preview(client, goal)
    unit = goal["units"][0]["id"]
    if mutation == "learn":
        client.post(f"/api/units/{unit}/learn", json={"reflection": "函数接收明确的输入并返回输出，需要通过边界案例和实际计算进行检验。"})
    elif mutation == "chat":
        client.post(f"/api/units/{unit}/chat", json={"message": "保留新聊天"})
    elif mutation == "metadata":
        client.patch(f"/api/goals/{goal['id']}", json={"version": 1, "title": "新的学习目标"})
    elif mutation == "other_course":
        assert apply(client, goal, preview(client, goal), key="another-confirmation").status_code == 200
    else:
        client.delete(f"/api/goals/{goal['id']}")
    result = apply(client, goal, change)
    assert result.status_code == (404 if mutation == "delete" else 409), result.text
    if mutation != "delete":
        assert result.json()["code"] == "course_conflict"
        assert len(client.get(path(goal)).json()["history"]) == (1 if mutation == "other_course" else 0)


def test_learning_during_generation_invalidates_preview_without_locking_writer(api, monkeypatch):
    client, application, module = api
    goal = create_goal(client)
    started, release = Event(), Event()
    generator = module.regenerate_units
    async def delayed(*args):
        started.set()
        assert await asyncio.to_thread(release.wait, 10)
        return await generator(*args)
    monkeypatch.setattr(module, "regenerate_units", delayed)
    with ThreadPoolExecutor() as pool:
        request = pool.submit(client.post, path(goal) + "/preview", json={"course_version": 1, "kind": "regenerate"})
        try:
            assert started.wait(10)
            assert client.post(f"/api/units/{goal['units'][0]['id']}/chat", json={"message": "生成期间也可以保存"}).status_code == 200
        finally:
            release.set()
        assert request.result().status_code == 409
    with application.state.session_factory() as db:
        assert db.scalar(select(CourseChange)) is None


@pytest.mark.parametrize("with_key", [False, True])
def test_competing_app_instances_confirm_only_one_course(api, monkeypatch, with_key):
    client, application, module = api
    goal = create_goal(client)
    first, second = preview(client, goal), preview(client, goal)
    lock = courses.lock_snapshot
    barrier = Barrier(2)
    def race(*args, **kwargs):
        barrier.wait(timeout=10)
        return lock(*args, **kwargs)
    monkeypatch.setattr(courses, "lock_snapshot", race)
    other_app = module.create_app(str(application.state.engine.url))
    with TestClient(other_app) as other, ThreadPoolExecutor() as pool:
        a = pool.submit(apply, client, goal, first, "competing-first" if with_key else None)
        b = pool.submit(apply, other, goal, second, "competing-second" if with_key else None)
        assert sorted([a.result().status_code, b.result().status_code]) == [200, 409]
    assert len(client.get(path(goal)).json()["history"]) == 1
    assert client.get(f"/api/goals/{goal['id']}").json()["course_version"] == 2


def test_inflight_chat_cannot_commit_after_unit_replacement(api, monkeypatch):
    client, _, module = api
    goal = create_goal(client)
    change = preview(client, goal)
    started, release = Event(), Event()
    async def delayed(*args):
        started.set()
        assert await asyncio.to_thread(release.wait, 10)
        return {"reply": "过期回复", "mode": "demo"}
    monkeypatch.setattr(module, "tutor_reply", delayed)
    with ThreadPoolExecutor() as pool:
        request = pool.submit(client.post, f"/api/units/{goal['units'][0]['id']}/chat", json={"message": "竞争聊天"})
        try:
            assert started.wait(10)
            assert apply(client, goal, change).status_code == 200
        finally:
            release.set()
        assert request.result().status_code == 409
    assert client.get(f"/api/units/{goal['units'][0]['id']}").json()["sessions"] == []


def test_preview_and_apply_replay_after_restart_backup_restore_and_delete(api, tmp_path):
    client, application, module = api
    goal = create_goal(client)
    payload = {"kind": "regenerate", "course_version": 1}
    headers = {"Idempotency-Key": "replay-course-preview"}
    first = client.post(path(goal) + "/preview", json=payload, headers=headers)
    assert first.status_code == 201
    change = first.json()
    saved = apply(client, goal, change)
    backup = tmp_path / "course-backup.db"
    backup_database(str(application.state.engine.url), backup)
    url = f"sqlite:///{tmp_path / 'restored.db'}"
    restore_database(backup, url)
    with TestClient(module.create_app(url)) as restored:
        replay = restored.post(path(goal) + "/preview", json=payload, headers=headers)
        assert replay.json() == change and replay.headers["Idempotency-Replayed"] == "true"
        replay = apply(restored, goal, change)
        assert replay.json() == saved.json() and replay.headers["Idempotency-Replayed"] == "true"
        assert apply(restored, goal, change, key="duplicate-preview-new-key").status_code == 409
        assert restored.get(path(goal)).json() == client.get(path(goal)).json()
        assert restored.get(f"/api/units/{goal['units'][0]['id']}").json()["archived"] is True
        assert restored.delete(f"/api/goals/{goal['id']}").status_code == 204
        assert restored.post(path(goal) + "/preview", json=payload, headers=headers).status_code == 410
        assert apply(restored, goal, change).status_code == 410
        with restored.app.state.session_factory() as db:
            assert db.scalar(select(CourseChange)) is None
            assert all(receipt.response_body is None for receipt in db.scalars(select(RequestReceipt)))


def test_receipt_failure_rolls_back_course_archives_and_history(api, monkeypatch):
    from app import idempotency
    client, application, _ = api
    goal = create_goal(client)
    change = preview(client, goal)
    finish = idempotency.finish
    def fail(*args, **kwargs):
        raise RuntimeError("simulated receipt failure")
    monkeypatch.setattr(idempotency, "finish", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        apply(client, goal, change)
    assert client.get(f"/api/goals/{goal['id']}").json() == goal
    assert client.get(path(goal)).json()["history"] == []
    with application.state.session_factory() as db:
        assert len(db.scalars(select(Unit)).all()) == 3
        assert db.get(Goal, goal["id"]).course_version == 1
    monkeypatch.setattr(idempotency, "finish", finish)
    assert apply(client, goal, change).status_code == 200


@pytest.mark.parametrize("fields", [
    {"kind": "difficulty", "level": "beginner"}, {"kind": "difficulty"},
    {"kind": "regenerate", "level": "advanced"}, {"kind": "regenerate", "course_version": True},
    {"kind": "reorder", "unit_ids": []}, {"kind": "regenerate", "material": {}},
])
def test_invalid_requests_do_not_mutate_course(api, fields):
    client, _, _ = api
    goal = create_goal(client)
    response = client.post(path(goal) + "/preview", json={"course_version": 1, **fields})
    assert response.status_code == 422, response.text
    assert client.get(f"/api/goals/{goal['id']}").json() == goal


def test_no_remaining_units_and_invalid_reorder_or_confirmation(api):
    client, _, _ = api
    goal = create_goal(client)
    ids = [unit["id"] for unit in goal["units"]]
    for ordered in (ids, [ids[0]] * 3, [*ids[:-1], "0" * 36]):
        assert client.post(path(goal) + "/preview", json={"course_version": 1, "kind": "reorder", "unit_ids": ordered}).status_code == 422
    change = preview(client, goal)
    for confirmed in (False, 1, "true"):
        assert client.post(path(goal) + "/apply", json={"preview_id": change["id"], "confirmed": confirmed}).status_code == 422
    other = create_goal(client)
    assert apply(client, other, change, key="wrong-goal-confirm").status_code == 404
    for unit_id in ids:
        client.post(f"/api/units/{unit_id}/chat", json={"message": "已开始"})
    assert client.post(path(goal) + "/preview", json={"course_version": 1, "kind": "regenerate"}).status_code == 409


@pytest.mark.parametrize("bad", [None, [], [{"title": "缺少内容"}]])
def test_malformed_plan_keeps_original_course(api, monkeypatch, bad):
    client, _, module = api
    goal = create_goal(client)
    async def broken(*args):
        return bad
    monkeypatch.setattr(module, "regenerate_units", broken)
    response = client.post(path(goal) + "/preview", json={"course_version": 1, "kind": "regenerate"})
    assert response.status_code == 502
    assert client.get(f"/api/goals/{goal['id']}").json() == goal
