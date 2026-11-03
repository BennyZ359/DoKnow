"""Learning evidence survives restarts, retries, provider changes and new practice rounds."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import importlib
import json
from threading import Barrier

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from app.data import backup_database, restore_database
from app.models import LearningSession, Unit, now_utc
from app.services import learning, providers


@pytest.fixture
def learning_api(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    monkeypatch.delenv("REDIS_URL", raising=False)
    module = importlib.import_module("app.main")
    app = module.create_app(f"sqlite:///{tmp_path / 'learning.db'}")
    with TestClient(app) as client:
        goal = client.post("/api/goals", json={"title": "Python"}).json()
        unit_id = goal["units"][0]["id"]
        response = client.post(f"/api/units/{unit_id}/learn", json={
            "reflection": "变量指向值，字符串和整数需要区分，通过转换再计算，并验证异常输入。",
        })
        assert response.status_code == 200
        yield client, app, module, unit_id


def answer_for(client, app, unit_id, *, correct=True):
    current = client.get(f"/api/units/{unit_id}").json()["practice"]
    with app.state.session_factory() as db:
        material = db.get(Unit, unit_id).material
        bank = [material["practice"], *material["practice_variants"]]
    item = bank[int(current["question_id"][1:]) - 1]
    answer = current["options"].index(item["options"][item["correct_index"]])
    if not correct:
        answer = (answer + 1) % len(current["options"])
    return {"answer": str(answer), "question_id": current["question_id"], "token": current["token"]}


def test_wrong_answer_rotates_and_all_distinct_questions_are_required(learning_api):
    client, app, module, unit_id = learning_api
    path = f"/api/units/{unit_id}"
    first = answer_for(client, app, unit_id, correct=False)
    wrong = client.post(f"{path}/practice", json=first).json()
    assert not wrong["passed"] and not wrong["practice_complete"]
    assert wrong["unit"]["practice"]["question_id"] != first["question_id"]
    assert wrong["unit"]["practice"]["correct"] == 0
    assert wrong["assessment"]["selected_answer"] != wrong["assessment"]["correct_answer"]
    assert wrong["assessment"]["question_source"]["source"] == "demo"
    assert client.post(f"{path}/practice", json=first).status_code == 409
    second = client.post(f"{path}/practice", json=answer_for(client, app, unit_id)).json()
    assert second["passed"] and second["unit"]["stage"] == "practice"
    assert not second["practice_complete"]
    assert client.post(f"{path}/project", json={"content": "这里有足够长的文字，但尚未完成所有题目的检验，不能进入实战。"}).status_code == 409
    reopened = module.create_app(str(app.state.engine.url))
    with TestClient(reopened) as other:
        assert other.get(path).json()["practice"] == second["unit"]["practice"]
        third = other.post(f"{path}/practice", json=answer_for(other, reopened, unit_id)).json()
        assert third["unit"]["practice"]["is_retry"]
        assert third["unit"]["practice"]["question_id"] == first["question_id"]
        final = other.post(f"{path}/practice", json=answer_for(other, reopened, unit_id)).json()
    assert final["practice_complete"] and final["unit"]["stage"] == "project"
    attempts = [s for s in final["unit"]["sessions"] if s["kind"] == "practice"]
    assert len(attempts) == 4
    assert [s["score"] for s in attempts] == [0, 100, 100, 100]
    assert len({s["assessment"]["question_id"] for s in attempts if s["score"] == 100}) == 3
    assert attempts[-1]["assessment"]["was_retry"]
    assert attempts[0]["assessment"] == wrong["assessment"]


@pytest.mark.parametrize("change,status", [
    ({"question_id": None}, 409), ({"token": None}, 409), ({"question_id": "q2"}, 409),
    ({"token": "999:0"}, 409), ({"answer": "-1"}, 422), ({"answer": "99"}, 422),
])
def test_invalid_and_unidentified_answers_never_advance(learning_api, change, status):
    client, app, _, unit_id = learning_api
    path = f"/api/units/{unit_id}"
    before = client.get(path).json()
    body = answer_for(client, app, unit_id) | change
    assert client.post(f"{path}/practice", json=body).status_code == status
    assert client.get(path).json() == before


def test_no_future_answers_leak_and_option_order_survives_reads(learning_api):
    client, app, _, unit_id = learning_api
    path = f"/api/units/{unit_id}"
    initial = client.get(path)
    assert "correct_index" not in initial.text and "practice_variants" not in initial.text
    with app.state.session_factory() as db:
        future = db.get(Unit, unit_id).material["practice_variants"][0]
    assert future["question"] not in initial.text
    assert future["explanation"] not in initial.text
    assert client.get(path).json()["practice"] == initial.json()["practice"]
    result = client.post(f"{path}/practice", json=answer_for(client, app, unit_id)).json()
    assert "correct_index" not in json.dumps(result)
    assert result["unit"]["practice"]["question"] == future["question"]
    assert future["explanation"] not in json.dumps(result, ensure_ascii=False)


def test_practice_receipt_replay_after_restart_cannot_answer_the_next_question(learning_api):
    client, app, module, unit_id = learning_api
    path = f"/api/units/{unit_id}"
    body = answer_for(client, app, unit_id, correct=False)
    headers = {"Idempotency-Key": "practice-attempt-replay"}
    original = client.post(f"{path}/practice", json=body, headers=headers)
    assert original.status_code == 200
    reopened = module.create_app(str(app.state.engine.url))
    with TestClient(reopened) as other:
        replay = other.post(f"{path}/practice", json=body, headers=headers)
        assert replay.json() == original.json()
        assert replay.headers["Idempotency-Replayed"] == "true"
        next_answer = answer_for(other, reopened, unit_id)
        assert other.post(f"{path}/practice", json=next_answer, headers=headers).status_code == 409
        current = other.get(path).json()
    assert current["practice"]["attempt"] == 2
    assert len([s for s in current["sessions"] if s["kind"] == "practice"]) == 1


def test_two_concurrent_submissions_cannot_count_as_two_questions(learning_api, monkeypatch):
    client, app, module, unit_id = learning_api
    body = answer_for(client, app, unit_id)
    barrier = Barrier(2)
    original = module.grade_practice

    def synchronized(*args):
        barrier.wait(timeout=5)
        return original(*args)

    monkeypatch.setattr(module, "grade_practice", synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(f"/api/units/{unit_id}/practice", json=body), range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    unit = client.get(f"/api/units/{unit_id}").json()
    assert unit["practice"]["correct"] == 1 and unit["practice"]["attempt"] == 2


@pytest.mark.parametrize("previous_reviews", [0, 2])
def test_failed_recall_starts_new_round_without_reusing_old_completion(learning_api, previous_reviews):
    client, app, _, unit_id = learning_api
    path = f"/api/units/{unit_id}"
    first_body = answer_for(client, app, unit_id)
    for _ in range(3):
        assert client.post(f"{path}/practice", json=answer_for(client, app, unit_id)).status_code == 200
    with app.state.session_factory() as db:
        unit = db.get(Unit, unit_id)
        unit.stage = "complete"
        unit.review_count = previous_reviews
        unit.review_due_at = now_utc() - timedelta(minutes=1)
        db.commit()
    failed = client.post(f"{path}/review", json={"rating": 1, "answer": "我只记得看过这些文字，但现在还无法独立说明概念与应用条件。"}).json()
    assert not failed["passed"] and failed["unit"]["stage"] == "practice"
    practice = failed["unit"]["practice"]
    assert practice["correct"] == 0 and practice["remaining"] == 3 and practice["round"] == 2
    assert practice["question_id"] != first_body["question_id"]
    assert client.post(f"{path}/practice", json=first_body).status_code == 409
    assert failed["assessment"]["source"] == "demo"


def test_successful_recalls_keep_round_and_later_failures_increment_once(learning_api):
    client, app, _, unit_id = learning_api
    path = f"/api/units/{unit_id}"
    recall = "变量是指向值的名字，字符串与整数用途不同，例如 int('4') * 3 得到数值 12。注意无效输入不能转换，需要捕获错误。"
    for expected_round in (1, 2):
        for _ in range(3):
            response = client.post(f"{path}/practice", json=answer_for(client, app, unit_id))
            assert response.status_code == 200
        completed = response.json()["unit"]["practice"]
        assert completed["round"] == expected_round and completed["remaining"] == 0
        # Isolate review scheduling while exercising real evaluation and round transitions.
        for rating in (4, 4, 1):
            with app.state.session_factory() as db:
                unit = db.get(Unit, unit_id)
                unit.stage = "complete"
                unit.review_due_at = now_utc() - timedelta(minutes=1)
                db.commit()
            reviewed = client.post(f"{path}/review", json={"rating": rating, "answer": recall}).json()
            if rating == 4:
                assert reviewed["passed"]
                assert reviewed["unit"]["practice"] == completed
            else:
                assert not reviewed["passed"] and reviewed["assessment"]["evaluation_passed"]
                assert reviewed["unit"]["practice"]["round"] == expected_round + 1
                assert reviewed["unit"]["practice"]["remaining"] == 3
                assert reviewed["unit"]["practice"]["correct"] == 0
    assert reviewed["unit"]["review_count"] == 6


def test_legacy_evaluations_remain_unknown_even_after_provider_changes(learning_api, monkeypatch):
    client, app, _, unit_id = learning_api
    with app.state.session_factory() as db:
        db.add(LearningSession(unit_id=unit_id, kind="project", content="旧作品", feedback="旧评价", score=85))
        db.commit()
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_MODEL", "different-model")
    session = client.get(f"/api/units/{unit_id}").json()["sessions"][-1]
    assert session["assessment"] == {"source": "unknown"}
    assert client.get("/api/dashboard").json()["recent_activity"][0]["assessment"] == {"source": "unknown"}


def test_ai_provenance_is_captured_per_request_and_persisted_on_failed_evaluations(learning_api, monkeypatch):
    client, app, _, unit_id = learning_api
    with app.state.session_factory() as db:
        db.get(Unit, unit_id).stage = "project"
        db.commit()
    real_client = httpx.AsyncClient
    requested = []

    def handler(request):
        model = json.loads(request.content)["model"]
        requested.append(model)
        monkeypatch.setenv("AI_MODEL", "changed-during-response")
        return httpx.Response(200, json={"model": f"{model}-snapshot", "unrelated": "test-secret-key",
                                      "choices": [{"message": {"content": json.dumps({
                                          "score": 40, "passed": False, "feedback": "需要补充输入与边界验证。",
                                      })}}]})

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")
    monkeypatch.setenv("AI_BASE_URL", "https://model.example/v1")
    for model in ["model-a", "model-b"]:
        monkeypatch.setenv("AI_MODEL", model)
        response = client.post(f"/api/units/{unit_id}/project", json={"content": "这里是需要模型检查的方案和具体结果，并指出还要验证的边界。"})
        assert response.status_code == 200
        evidence = response.json()["assessment"]
        assert evidence == {"source": "ai", "provider": "compatible", "model": f"{model}-snapshot",
                            "requested_model": model, "rule_version": "semantic-v1", "passed": False}
        assert "test-secret-key" not in response.text
    attempts = client.get(f"/api/units/{unit_id}").json()["sessions"][-2:]
    assert [item["assessment"]["requested_model"] for item in attempts] == requested == ["model-a", "model-b"]
    assert all(item["score"] == 40 for item in attempts)


def test_backup_restore_keeps_practice_progress_and_assessment_history(learning_api, tmp_path):
    client, app, module, unit_id = learning_api
    path = f"/api/units/{unit_id}"
    client.post(f"{path}/practice", json=answer_for(client, app, unit_id, correct=False))
    expected = client.get(path).json()
    backup = tmp_path / "snapshot.db"
    restored = tmp_path / "restored.db"
    backup_database(str(app.state.engine.url), backup)
    restore_database(backup, f"sqlite:///{restored}")
    reopened = module.create_app(f"sqlite:///{restored}")
    with TestClient(reopened) as other:
        assert other.get(path).json() == expected
        assert other.post(f"{path}/practice", json=answer_for(other, reopened, unit_id)).json()["passed"]
    with app.state.session_factory() as db:
        assert len(db.scalars(select(LearningSession).where(LearningSession.kind == "practice")).all()) == 1


def test_duplicate_or_missing_variant_questions_are_rejected():
    unit = learning._demo_plan("Python", "beginner", 30)[0]
    unit["practice_variants"][0] = unit["practice"]
    with pytest.raises(ValueError, match="different questions"):
        learning.PlanUnit.model_validate(unit)
    unit["practice_variants"] = []
    with pytest.raises(ValueError):
        learning.PlanUnit.model_validate(unit)
