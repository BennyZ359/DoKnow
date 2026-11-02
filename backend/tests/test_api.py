"""The learning cycle is advanced by recorded evidence, not UI navigation."""

from copy import deepcopy
from datetime import timedelta
import importlib
import json

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.models import Goal, KnowledgeEntry, LearningSession, Unit, now_utc


PLAN = [{
    "title": f"Python 函数 · 单元 {position + 1}",
    "objective": "用明确输入输出解释 Python 函数，检验边界情况。",
    "lesson": {"explanation": "函数将输入映射到输出，参数表示输入，return 表示返回。", "example": "def double(x): return x * 2", "question": "输出和打印有什么区别？"},
    "practice": {"question": "哪一个返回双倍值？", "options": ["print(x)", "return x * 2", "x + 2"], "correct_index": 1, "explanation": "return x * 2 返回双倍值，print 只打印。"},
    "project": {"title": "完成函数", "brief": "定义 double 函数，并测试输入和结果。", "criteria": ["实现", "示例", "边界"]},
    "teach": {"prompt": "向初学者讲解函数。", "checklist": ["概念", "例子", "边界"]},
} for position in range(3)]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    module = importlib.import_module("app.main")

    async def plan(*_):
        return deepcopy(PLAN)

    async def evaluate(kind, unit, content):
        passed = "充分证据" in content
        return {"score": 85 if passed else 25, "passed": passed, "feedback": f"{kind}：已检查概念、例子与边界。"}

    async def reply(*_):
        return {"reply": "先举一个输入，再预测输出。为什么？", "mode": "demo"}

    monkeypatch.setattr(module, "generate_plan", plan)
    monkeypatch.setattr(module, "evaluate_submission", evaluate)
    monkeypatch.setattr(module, "tutor_reply", reply)
    application = module.create_app(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(application) as client:
        yield client, application, module


def create_goal(client):
    response = client.post("/api/goals", json={"title": "学习 Python 函数", "motivation": "用代码解决重复计算", "daily_minutes": 30})
    assert response.status_code == 201, response.text
    return response.json()


def make_due(application, unit_id):
    with application.state.session_factory() as db:
        unit = db.get(Unit, unit_id)
        unit.review_due_at = now_utc() - timedelta(minutes=1)
        db.commit()


def complete_until_review(client, unit_id):
    reflection = "我理解函数接受输入并返回结果，输出需要用 return 明确表达，打印只是显示。"
    assert client.post(f"/api/units/{unit_id}/learn", json={"reflection": reflection}).status_code == 200
    assert client.post(f"/api/units/{unit_id}/practice", json={"answer": "1"}).json()["passed"] is True
    content = "充分证据：我实现了 double 函数，将输入 3 变成结果 6，并测试输入 0 和负数的边界。"
    assert client.post(f"/api/units/{unit_id}/project", json={"content": content}).json()["passed"] is True
    assert client.post(f"/api/units/{unit_id}/teach", json={"content": content}).json()["passed"] is True
    response = client.post(f"/api/units/{unit_id}/reflect", json={
        "content": "通过实践发现，理解函数必须区别返回值和打印，这改变了我原来模糊的认识。",
        "takeaway": "函数的输入输出可以用实例逐一验证。",
        "change": "我以前只关注显示结果，现在更关注可复用的返回值。",
    })
    assert response.status_code == 200, response.text
    assert response.json()["unit"]["stage"] == "review"


def test_health_settings_no_secret(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv("AI_API_KEY", "private-secret-must-never-be-exposed")
    assert client.get("/api/health").json() == {"status": "ok", "mode": "demo", "database": "sqlite"}
    response = client.get("/api/settings")
    assert len(response.json()["principles"]) == 7
    assert "private-secret" not in response.text
    assert client.get("/api/dashboard").json()["goals"] == []


def test_plan_validation_and_hidden_answers(api):
    client, _, _ = api
    assert client.post("/api/goals", json={"title": "x", "daily_minutes": 4}).status_code == 422
    goal = create_goal(client)
    assert goal["progress"] == 0
    assert len(goal["units"]) == 3
    unit = client.get(f"/api/units/{goal['units'][0]['id']}").json()
    assert "correct_index" not in unit["practice"]
    assert "explanation" not in unit["practice"]
    assert unit["sessions"] == []
    assert client.get(f"/api/goals/{goal['id']}").json()["title"] == goal["title"]


def test_sequential_gates_and_real_choice_grading(api):
    client, _, _ = api
    unit_id = create_goal(client)["units"][0]["id"]
    path = f"/api/units/{unit_id}"
    assert client.post(f"{path}/practice", json={"answer": "1"}).status_code == 409
    assert client.post(f"{path}/project", json={"content": "提前提交完整的实践，但是还没有完成学习和练习阶段。"}).status_code == 409
    assert client.post(f"{path}/learn", json={"reflection": " " * 50}).status_code == 422
    assert client.post(f"{path}/learn", json={"reflection": "我理解了函数的输入和输出，需要通过具体例子验证返回值的行为。"}).status_code == 200
    assert client.post(f"{path}/learn", json={"reflection": "我理解了函数的输入和输出，需要通过具体例子验证返回值的行为。"}).status_code == 409
    assert client.post(f"{path}/practice", json={"answer": "-1"}).status_code == 422
    assert client.post(f"{path}/practice", json={"answer": "9"}).status_code == 422
    wrong = client.post(f"{path}/practice", json={"answer": "0"}).json()
    assert wrong["passed"] is False and wrong["score"] == 0
    assert wrong["unit"]["stage"] == "practice"
    assert "return" in wrong["feedback"]
    right = client.post(f"{path}/practice", json={"answer": "1"}).json()
    assert right["passed"] is True and right["unit"]["stage"] == "project"
    assert right["unit"]["mastery"] == 35
    assert client.post(f"{path}/practice", json={"answer": "1"}).status_code == 409
    weak = client.post(f"{path}/project", json={"content": "我觉得已经学会了，也尝试写了一些代码，但尚未验证输入与结果。"}).json()
    assert weak["passed"] is False and weak["unit"]["stage"] == "project"
    assert len(client.get(path).json()["sessions"]) == 4


def test_full_loop_persisted_reflection_and_interval_recall(api):
    client, application, _ = api
    goal = create_goal(client)
    unit_id = goal["units"][0]["id"]
    complete_until_review(client, unit_id)
    assert client.get("/api/reviews").json() == []
    notes = client.get("/api/knowledge").json()
    assert len(notes) == 1 and notes[0]["source"] == "reflection"
    assert "体验与认识的变化" in notes[0]["content"]
    recall = {"rating": 3, "answer": "充分证据：函数接收输入并通过 return 返回输出，例如输入 3 得到结果 6，零和负数也是边界。"}
    assert client.post(f"/api/units/{unit_id}/review", json=recall).status_code == 409
    make_due(application, unit_id)
    assert client.get("/api/dashboard").json()["reviews_due"] == 1
    assert client.get("/api/reviews").json()[0]["id"] == unit_id
    reviewed = client.post(f"/api/units/{unit_id}/review", json=recall).json()
    assert reviewed["passed"] is True
    assert reviewed["unit"]["stage"] == "complete"
    assert reviewed["unit"]["review_count"] == 1
    assert reviewed["unit"]["completed_at"] is not None
    assert client.get("/api/dashboard").json()["reviews_due"] == 0
    assert len(client.get(f"/api/units/{unit_id}").json()["sessions"]) == 6
    # A finished unit remains eligible for future recall.
    make_due(application, unit_id)
    assert len(client.get("/api/reviews").json()) == 1
    with application.state.session_factory() as db:
        assert db.get(Unit, unit_id).stage == "complete"
        assert db.scalar(select(func.count()).select_from(LearningSession)) == 6


@pytest.mark.parametrize("answer,rating", [("我只记得看过这些内容，但是现在还不能解释函数的输入和返回值以及边界。", 4), ("充分证据：函数接收输入并返回输出，例如输入 3 得到结果 6，零和负数也是边界。", 1)])
def test_recall_evidence_overrules_self_rating(api, answer, rating):
    client, application, _ = api
    unit_id = create_goal(client)["units"][0]["id"]
    complete_until_review(client, unit_id)
    make_due(application, unit_id)
    response = client.post(f"/api/units/{unit_id}/review", json={"rating": rating, "answer": answer}).json()
    assert response["passed"] is False
    assert response["unit"]["stage"] == "practice"
    assert response["unit"]["review_due_at"] is None
    assert response["unit"]["completed_at"] is None


def test_chat_history_never_advances_stage(api):
    client, _, _ = api
    unit_id = create_goal(client)["units"][0]["id"]
    assert client.post(f"/api/units/{unit_id}/chat", json={"message": "我还不理解返回值，能用例子解释吗？"}).json()["mode"] == "demo"
    unit = client.get(f"/api/units/{unit_id}").json()
    assert unit["stage"] == "learn" and len(unit["sessions"]) == 1
    assert unit["sessions"][0]["kind"] == "chat"
    assert client.get("/api/dashboard").json()["total_sessions"] == 1


def test_knowledge_import_validation_and_citation_route(api):
    client, _, module = api
    note = client.post("/api/knowledge", json={"title": "函数笔记", "content": "Python 函数的参数是输入，return 返回输出，print 用于显示。"})
    assert note.status_code == 201
    imported = client.post("/api/knowledge/import", files={"file": ("../../函数.md", "# 函数\n函数用参数接收输入，用 return 返回输出。".encode(), "text/markdown")})
    assert imported.status_code == 201, imported.text
    assert imported.json()["source"] == "函数.md"
    assert client.post("/api/knowledge/import", files={"file": ("payload.exe", b"invalid", "application/octet-stream")}).status_code == 422
    assert client.post("/api/knowledge/import", files={"file": ("empty.txt", b"", "text/plain")}).status_code == 422
    assert client.post("/api/knowledge/import", files={"file": ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")}).status_code == 413
    asked = client.post("/api/knowledge/ask", json={"question": "函数输入输出是什么？"})
    assert asked.status_code == 200, asked.text
    assert asked.json()["sources"]
    assert client.delete(f"/api/knowledge/{note.json()['id']}").status_code == 204
    assert client.delete(f"/api/knowledge/{note.json()['id']}").status_code == 404


def test_goal_delete_cascades_sessions_and_units_preserves_notes(api):
    client, application, _ = api
    goal = create_goal(client)
    unit_id = goal["units"][0]["id"]
    complete_until_review(client, unit_id)
    assert client.delete(f"/api/goals/{goal['id']}").status_code == 204
    assert client.get(f"/api/units/{unit_id}").status_code == 404
    assert client.get("/api/goals").json() == []
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Goal)) == 0
        assert db.scalar(select(func.count()).select_from(Unit)) == 0
        assert db.scalar(select(func.count()).select_from(LearningSession)) == 0
        note = db.scalar(select(KnowledgeEntry))
        assert note is not None and note.unit_id is None


def test_invalid_upstream_plan_is_not_persisted(api, monkeypatch):
    client, _, module = api

    async def invalid(*_):
        return [{"title": "bad"}]

    monkeypatch.setattr(module, "generate_plan", invalid)
    assert client.post("/api/goals", json={"title": "学习函数"}).status_code == 502
    assert client.get("/api/goals").json() == []


def test_provider_error_safe_and_no_progress_recorded(api, monkeypatch):
    client, _, module = api
    unit_id = create_goal(client)["units"][0]["id"]

    async def failed(*_):
        raise module.ProviderError("AI 服务暂时不可用，请稍后重试。")

    monkeypatch.setattr(module, "tutor_reply", failed)
    response = client.post(f"/api/units/{unit_id}/chat", json={"message": "请再举一个例子。"})
    assert response.status_code == 502
    assert response.json()["detail"] == "AI 服务暂时不可用，请稍后重试。"
    assert client.get(f"/api/units/{unit_id}").json()["sessions"] == []


def test_stale_concurrent_update_is_rejected(api):
    client, application, module = api
    unit_id = create_goal(client)["units"][0]["id"]
    with application.state.session_factory() as first, application.state.session_factory() as second:
        older = first.get(Unit, unit_id)
        newer = second.get(Unit, unit_id)
        newer.stage = "practice"
        second.commit()
        older.stage = "project"
        with pytest.raises(HTTPException) as error:
            module.save(first)
        assert error.value.status_code == 409
    assert client.get(f"/api/units/{unit_id}").json()["stage"] == "practice"


def test_database_survives_new_app_instance(api):
    client, application, module = api
    goal = create_goal(client)
    unit_id = goal["units"][0]["id"]
    client.post(f"/api/units/{unit_id}/chat", json={"message": "函数是什么？"})
    reopened = module.create_app(str(application.state.engine.url))
    with TestClient(reopened) as new_client:
        assert new_client.get(f"/api/goals/{goal['id']}").json()["title"] == goal["title"]
        assert len(new_client.get(f"/api/units/{unit_id}").json()["sessions"]) == 1


def test_invalid_rating_type_does_not_change_progress(api):
    client, application, _ = api
    unit_id = create_goal(client)["units"][0]["id"]
    complete_until_review(client, unit_id)
    make_due(application, unit_id)
    response = client.post(f"/api/units/{unit_id}/review", json={"rating": True, "answer": "我理解函数能够接收输入并通过返回值提供结果，需要使用例子来验证。"})
    assert response.status_code == 422
    assert client.get(f"/api/units/{unit_id}").json()["stage"] == "review"


def test_failed_recall_resets_spacing_streak(api):
    client, application, _ = api
    unit_id = create_goal(client)["units"][0]["id"]
    complete_until_review(client, unit_id)
    make_due(application, unit_id)
    with application.state.session_factory() as db:
        unit = db.get(Unit, unit_id)
        unit.review_count = 8
        unit.review_streak = 5
        db.commit()
    client.post(f"/api/units/{unit_id}/review", json={"rating": 1, "answer": "我已经忘记如何解释函数，虽然以前能回答，现在需要重新通过练习来验证。"})
    with application.state.session_factory() as db:
        unit = db.get(Unit, unit_id)
        assert unit.review_count == 9
        assert unit.review_streak == 0
        assert unit.stage == "practice"


def test_tutor_receives_failed_assessment_evidence(api, monkeypatch):
    client, _, module = api
    unit_id = create_goal(client)["units"][0]["id"]
    client.post(f"/api/units/{unit_id}/learn", json={"reflection": "我理解函数接受输入并返回输出，打印和返回需要通过具体例子来区分。"})
    client.post(f"/api/units/{unit_id}/practice", json={"answer": "0"})
    observed = []

    async def tutor(goal_title, unit, message, history):
        observed.extend(history)
        return {"reply": "对照刚才的错误答案，先区分打印和返回值。", "mode": "demo"}

    monkeypatch.setattr(module, "tutor_reply", tutor)
    assert client.post(f"/api/units/{unit_id}/chat", json={"message": "我为什么错了？"}).status_code == 200
    assert any(item["kind"] == "practice" and item["score"] == 0 for item in observed)


@pytest.mark.parametrize("invalid", ["\x00", "\ud800"])
def test_nonportable_text_rejected_before_database_write(api, invalid):
    client, application, _ = api

    def post_invalid(path, body):
        # Send an escaped surrogate as raw JSON; HTTP clients correctly refuse to
        # UTF-8 encode it directly, but a manually crafted request can contain it.
        return client.post(path, content=json.dumps(body, ensure_ascii=True), headers={"Content-Type": "application/json"})

    invalid_goal = post_invalid("/api/goals", {"title": f"学习 Python{invalid}"})
    assert invalid_goal.status_code == 422
    assert client.get("/api/goals").json() == []
    goal = create_goal(client)
    unit_id = goal["units"][0]["id"]
    assert post_invalid(f"/api/units/{unit_id}/chat", {"message": f"请解释函数{invalid}"}).status_code == 422
    assert post_invalid(f"/api/units/{unit_id}/learn", {"reflection": f"我理解函数接收输入并返回输出，应用时需要验证具体例子。{invalid}"}).status_code == 422
    assert post_invalid(f"/api/units/{unit_id}/project", {"content": f"实践程序计算输入和输出，并检查实际结果与边界条件。{invalid}"}).status_code == 422
    assert post_invalid("/api/knowledge", {"title": "有效笔记", "content": f"这份笔记描述函数的输入输出和边界条件。{invalid}"}).status_code == 422
    assert post_invalid("/api/knowledge/ask", {"question": f"函数是什么？{invalid}"}).status_code == 422
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningSession)) == 0
        assert db.scalar(select(func.count()).select_from(KnowledgeEntry)) == 0


def test_unicode_choice_digits_are_validated_without_server_error(api):
    client, _, _ = api
    unit_id = create_goal(client)["units"][0]["id"]
    client.post(f"/api/units/{unit_id}/learn", json={"reflection": "我理解函数接收输入并返回输出，需要通过运行不同例子来验证边界。"})
    # These are numeric Unicode characters, but not decimal digits accepted by int().
    for value in ("²", "Ⅳ", "①"):
        response = client.post(f"/api/units/{unit_id}/practice", json={"answer": value})
        assert response.status_code == 422
    # Arabic decimal digits identify the same option as their ASCII counterpart.
    response = client.post(f"/api/units/{unit_id}/practice", json={"answer": "١"})
    assert response.status_code == 200
    assert response.json()["passed"] is True


def test_validation_errors_do_not_echo_nonfinite_or_large_input(api):
    client, _, _ = api
    response = client.post("/api/goals", content='{"title":"Python","daily_minutes":NaN}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "NaN" not in response.text
    response = client.post("/api/knowledge", json={"title": "不应回显" * 1000, "content": "这是有效长度的笔记正文，但是标题长度不符合要求。"})
    assert response.status_code == 422
    assert len(response.content) < 2000
    assert all("input" not in error for error in response.json()["detail"])


def test_import_filename_must_be_portable_text(api):
    client, _, _ = api
    # Client multipart encoders normally escape NUL; exercise a crafted upload.
    boundary = "doknow-portable-file"
    body = b"\r\n".join([
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="file"; filename="bad\x00.md"',
        b"Content-Type: text/markdown", b"", b"# valid text with learning materials",
        f"--{boundary}--".encode(), b"",
    ])
    response = client.post("/api/knowledge/import", content=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert response.status_code == 422
    assert client.get("/api/knowledge").json() == []
