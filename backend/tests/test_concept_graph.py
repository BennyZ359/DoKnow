"""Semantic graph storage and queries are independent of lesson ordering."""

from copy import deepcopy
from importlib import import_module
import json

from fastapi.testclient import TestClient
from pydantic import ValidationError
import httpx
import pytest
from sqlalchemy import func, select

from app.models import ConceptGraph, KnowledgeEntity, KnowledgeRelation
from app.services import concept_graph, providers
from app.services.concept_catalog import catalog_graph


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    module = import_module("app.main")
    url = f"sqlite:///{tmp_path / 'concepts.db'}"
    application = module.create_app(url)
    with TestClient(application) as client:
        yield client, application, module, url


def build(client, topic="机器学习", headers=None):
    response = client.post("/api/graphs", json={"topic": topic}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("topic", ["机器学习", "Python", "前端开发", "AI Agent"])
def test_examples_are_connected_semantic_networks(topic):
    plan = concept_graph.ConceptGraphPlan.model_validate(catalog_graph(topic))
    assert len({edge.kind for edge in plan.relations}) >= 3
    assert any(edge.kind == "requires" for edge in plan.relations)
    assert all(not hasattr(node, "position") for node in plan.entities)


def test_semantic_cycles_and_parallel_relation_types_are_allowed():
    plan = catalog_graph("机器学习")
    # Both assertions can hold: an optimisation method uses a loss and optimises it.
    plan["relations"].append({"source": "gradient-descent", "target": "loss", "kind": "uses", "explanation": "该方法需要计算损失与梯度。"})
    plan["relations"].append({"source": "loss", "target": "gradient-descent", "kind": "applied_to", "explanation": "损失函数可作为梯度下降的目标函数。"})
    concept_graph.ConceptGraphPlan.model_validate(plan)


@pytest.mark.parametrize("fault", ["duplicate_entity", "missing_target", "duplicate_relation", "self", "orphan", "single_relation"])
def test_bad_assertions_are_rejected(fault):
    plan = catalog_graph("机器学习")
    if fault == "duplicate_entity":
        plan["entities"][0]["key"] = plan["entities"][1]["key"]
    elif fault == "missing_target":
        plan["relations"][0]["target"] = "missing"
    elif fault == "duplicate_relation":
        plan["relations"].append(deepcopy(plan["relations"][0]))
    elif fault == "self":
        plan["relations"][0]["target"] = plan["relations"][0]["source"]
    elif fault == "orphan":
        plan["entities"].append({**deepcopy(plan["entities"][0]), "key": "orphan", "name": "无关实体"})
    else:
        for edge in plan["relations"]:
            edge["kind"] = "requires"
    with pytest.raises(ValidationError):
        concept_graph.ConceptGraphPlan.model_validate(plan)


def test_entities_and_relations_are_persisted_rows_and_restore_after_restart(api):
    client, app, module, url = api
    graph = build(client, headers={"Idempotency-Key": "concept-graph-persist"})
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConceptGraph)) == 1
        assert db.scalar(select(func.count()).select_from(KnowledgeEntity)) == 31
        assert db.scalar(select(func.count()).select_from(KnowledgeRelation)) == 45
    assert client.post("/api/graphs", json={"topic": "机器学习"}, headers={"Idempotency-Key": "concept-graph-persist"}).json() == graph
    assert len(client.get("/api/graphs").json()) == 1
    with TestClient(module.create_app(url)) as restarted:
        assert restarted.get(f"/api/graphs/{graph['id']}").json() == graph


def test_alias_search_neighborhood_directions_and_relation_filter(api):
    client, _, _, _ = api
    graph = build(client)
    root = f"/api/graphs/{graph['id']}"
    found = client.get(root + "/entities", params={"q": "GD"}).json()
    assert [item["name"] for item in found] == ["梯度下降"]
    gd = found[0]["id"]
    full = client.get(f"{root}/neighbors/{gd}?depth=1").json()
    assert {item["name"] for item in full["entities"]} == {"梯度下降", "梯度", "学习率", "损失函数", "线性回归"}
    out = client.get(f"{root}/neighbors/{gd}?depth=1&relation=requires&direction=out").json()
    assert {item["name"] for item in out["entities"]} == {"梯度下降", "梯度"}
    assert len(out["relations"]) == 1 and out["relations"][0]["source"] == gd
    inward = client.get(f"{root}/neighbors/{gd}?depth=1&relation=uses&direction=in").json()
    assert {item["name"] for item in inward["entities"]} == {"梯度下降", "线性回归"}
    assert len(client.get(root + "/entities?kind=tool").json()) == 3
    assert client.get(f"{root}/neighbors/{gd}?depth=4").status_code == 422
    assert client.get(f"{root}/neighbors/{gd}?relation=unknown").status_code == 422


def test_shortest_path_is_semantic_and_preserves_direction(api):
    client, _, _, _ = api
    graph = build(client)
    ids = {node["key"]: node["id"] for node in graph["entities"]}
    root = f"/api/graphs/{graph['id']}/path"
    params = {"source": ids["gradient-descent"], "target": ids["derivative"], "relation": "requires", "direction": "out"}
    route = client.get(root, params=params).json()
    assert route["found"] and route["entity_ids"] == [ids["gradient-descent"], ids["gradient"], ids["derivative"]]
    assert len(route["relation_ids"]) == 2
    params["source"], params["target"] = params["target"], params["source"]
    assert not client.get(root, params=params).json()["found"]
    params["direction"] = "both"
    assert client.get(root, params=params).json()["found"]
    params["target"] = params["source"]
    assert client.get(root, params=params).json()["entity_ids"] == [params["source"]]


def test_graph_queries_cannot_follow_entities_from_another_graph(api):
    client, _, _, _ = api
    first, second = build(client), build(client, "Python")
    other = second["focus_id"]
    assert client.get(f"/api/graphs/{first['id']}/neighbors/{other}").status_code == 404
    assert client.get(f"/api/graphs/{first['id']}/path?source={first['focus_id']}&target={other}").status_code == 404


def test_failed_model_and_bad_graph_leave_no_rows_or_completed_receipt(api, monkeypatch):
    client, app, module, _ = api
    original = module.generate_concept_graph
    async def bad(_):
        result = catalog_graph("机器学习")
        result["relations"][0]["target"] = "nonexistent"
        return {**result, "source": "ai"}
    monkeypatch.setattr(module, "generate_concept_graph", bad)
    headers = {"Idempotency-Key": "graph-bad-model-retry"}
    assert client.post("/api/graphs", json={"topic": "机器学习"}, headers=headers).status_code == 502
    assert client.get("/api/graphs").json() == []
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(KnowledgeEntity)) == 0
    monkeypatch.setattr(module, "generate_concept_graph", original)
    build(client, headers=headers)


async def test_model_prompt_requests_semantic_assertions_and_marks_them_unverified(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.setenv("AI_BASE_URL", "https://model.example/v1")
    original = httpx.AsyncClient
    def reply(request):
        payload = json.loads(request.content)
        assert "不要把图谱强制排成 DAG" in payload["messages"][0]["content"]
        assert json.loads(payload["messages"][-1]["content"])["topic"] == "机器人"
        return httpx.Response(200, json={"model": "reported", "choices": [{"message": {"content": json.dumps(catalog_graph("机器学习"))}}]})
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(reply)))
    result = await concept_graph.generate_concept_graph("机器人")
    assert result["source"] == "ai" and result["model"] == "reported"
