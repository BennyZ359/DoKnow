"""Graph semantics, model boundaries, persistence and safe retries."""

import json
from copy import deepcopy
from importlib import import_module

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.services import providers, roadmaps


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    module = import_module("app.main")
    url = f"sqlite:///{tmp_path / 'roadmaps.db'}"
    with TestClient(module.create_app(url)) as client:
        yield client, module, url


@pytest.mark.parametrize("topic, expected", [
    ("我想从零学习机器学习", "线性代数基础"), ("Python", "文件读写与异常处理"),
    ("前端开发", "HTML 语义与结构"), ("AI Agent", "智能体执行循环"),
    ("英语口语", "基础发音与听辨"), ("深度学习", "神经网络与反向传播"),
])
def test_examples_have_real_prerequisites_and_parallel_branches(topic, expected):
    plan = roadmaps.demo_plan(topic)
    assert expected in [node["title"] for node in plan["nodes"]]
    assert plan["source"] == "demo" and "离线" in plan["source_note"]
    seen = set()
    for node in plan["nodes"]:
        assert set(node["prerequisites"]) <= seen
        seen.add(node["id"])
    assert plan["nodes"][-1]["id"] == plan["target_node_id"]
    assert any(len(node["prerequisites"]) > 1 for node in plan["nodes"])


@pytest.mark.parametrize("fault", ["cycle", "missing", "duplicate", "orphan", "self", "title", "hours"])
def test_rejects_invalid_graphs(fault):
    plan = roadmaps.demo_plan("机器学习")
    plan = {key: plan[key] for key in ("objective", "assumptions", "target_node_id", "nodes")}
    nodes = plan["nodes"]
    if fault == "cycle":
        nodes[0]["prerequisites"] = [plan["target_node_id"]]
    elif fault == "missing":
        nodes[-1]["prerequisites"] = ["missing"]
    elif fault == "duplicate":
        nodes[0]["id"] = nodes[1]["id"]
    elif fault == "orphan":
        plan["nodes"].append({**deepcopy(nodes[0]), "id": "orphan", "title": "无关知识"})
    elif fault == "self":
        nodes[0]["prerequisites"] = [nodes[0]["id"]]
    elif fault == "title":
        nodes[0]["title"] = nodes[1]["title"]
    elif fault == "hours":
        nodes[0]["estimated_hours"] = 0
    with pytest.raises(ValidationError):
        roadmaps.RoadmapPlan.model_validate(plan)


def test_create_replay_and_restart_preserve_graph(api):
    client, module, url = api
    headers = {"Idempotency-Key": "roadmap-create-123"}
    first = client.post("/api/roadmaps", json={"topic": "  机器学习  "}, headers=headers)
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["topic"] == "机器学习"
    replay = client.post("/api/roadmaps", json={"topic": "  机器学习  "}, headers=headers)
    assert replay.json() == result
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert client.post("/api/roadmaps", json={"topic": "Python"}, headers=headers).status_code == 409
    assert len(client.get("/api/roadmaps").json()) == 1
    assert client.get("/api/goals").json() == []
    with TestClient(module.create_app(url)) as restarted:
        assert restarted.get(f"/api/roadmaps/{result['id']}").json() == result
        summary = restarted.get("/api/roadmaps").json()[0]
        assert summary["node_count"] == len(result["nodes"])
        assert "nodes" not in summary


@pytest.mark.parametrize("topic", ["", "   ", "x" * 201, "\x00", "\ud800"])
def test_invalid_input_is_not_saved(api, topic):
    client, _, _ = api
    response = client.post("/api/roadmaps", content=json.dumps({"topic": topic}), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert client.get("/api/roadmaps").json() == []


def test_unknown_demo_topic_is_explicit_and_does_not_fake_a_plan(api):
    client, _, _ = api
    response = client.post("/api/roadmaps", json={"topic": "古典吉他"})
    assert response.status_code == 422
    assert "暂未收录" in response.json()["detail"]
    assert client.get("/api/roadmaps").json() == []
    assert client.get("/api/roadmaps/missing").status_code == 404


def test_invalid_provider_graph_is_not_persisted(api, monkeypatch):
    client, module, _ = api
    async def broken(_):
        plan = roadmaps.demo_plan("Python")
        plan["nodes"][0]["prerequisites"] = [plan["target_node_id"]]
        return plan
    monkeypatch.setattr(module, "generate_roadmap", broken)
    response = client.post("/api/roadmaps", json={"topic": "Python"})
    assert response.status_code == 502
    assert client.get("/api/roadmaps").json() == []


async def test_compatible_provider_receives_topic_and_validates_graph(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "fake-test-key")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.setenv("AI_BASE_URL", "https://model.example/v1")
    plan = roadmaps.demo_plan("英语")
    plan = {key: plan[key] for key in ("objective", "assumptions", "target_node_id", "nodes")}
    real_client = httpx.AsyncClient
    def response(request):
        payload = json.loads(request.content)
        assert json.loads(payload["messages"][-1]["content"])["topic"] == "我会基础词汇，想练旅行英语"
        assert payload["response_format"]["type"] == "json_object"
        assert "prerequisites" in payload["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan)}}]})
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(response)))
    result = await roadmaps.generate_roadmap("我会基础词汇，想练旅行英语")
    assert result["source"] == "ai"
    assert result["nodes"] == plan["nodes"]


def test_provider_failure_does_not_fall_back_and_can_retry_same_operation(api, monkeypatch):
    client, module, _ = api
    async def unavailable(_):
        raise providers.ProviderError("模型暂时无法连接")
    original = module.generate_roadmap
    monkeypatch.setattr(module, "generate_roadmap", unavailable)
    headers = {"Idempotency-Key": "roadmap-retry-123"}
    assert client.post("/api/roadmaps", json={"topic": "Python"}, headers=headers).status_code == 502
    assert client.get("/api/roadmaps").json() == []
    monkeypatch.setattr(module, "generate_roadmap", original)
    assert client.post("/api/roadmaps", json={"topic": "Python"}, headers=headers).status_code == 201
    assert len(client.get("/api/roadmaps").json()) == 1
