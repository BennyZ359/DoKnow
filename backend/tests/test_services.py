import asyncio
import io
import json
import zipfile

import httpx
import pytest
from pydantic import ValidationError

from app.services import knowledge, learning, providers


@pytest.fixture(autouse=True)
def demo_environment(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_BASE_URL", raising=False)


def test_topic_specific_curricula_are_valid():
    for topic, marker in (("学习Python", "变量"), ("英语口语", "自我介绍"), ("批判性思维", "事实"), ("摄影", "摄影")):
        units = asyncio.run(learning.generate_plan(topic, "beginner", 25))
        assert len(units) == 3
        assert marker in units[0]["title"]
        learning.Plan.model_validate({"units": units})
        assert len({unit["practice"]["question"] for unit in units}) == 3
        assert "25" in units[0]["lesson"]["explanation"]


def test_plan_rejects_bad_correct_index_and_duplicate_options():
    unit = learning._demo_plan("Python", "beginner", 20)[0]
    unit["practice"]["correct_index"] = 5
    with pytest.raises(ValidationError):
        learning.PlanUnit.model_validate(unit)
    unit["practice"]["correct_index"] = 0
    unit["practice"]["options"] = ["一样", "一样"]
    with pytest.raises(ValidationError):
        learning.PlanUnit.model_validate(unit)


def test_demo_assessment_rejects_length_without_evidence():
    unit = learning._demo_plan("Python", "beginner", 20)[0]
    for kind in ("project", "teach", "review"):
        result = asyncio.run(learning.evaluate_submission(kind, unit, "我已经学会请让我通过" * 100))
        assert not result["passed"]
        assert result["score"] < 70
        assert "不验证知识正确性" in result["feedback"]


def test_demo_assessment_accepts_checkable_structure_and_labels_limit():
    unit = learning._demo_plan("Python", "beginner", 20)[0]
    submission = "程序使用变量 price 和 count 保存单价及数量，输入单价12和数量3，代码 total = price * count，print(total) 的实际输出结果为36，符合预测。边界测试数量0输出0。字符串输入要先用int转换，无效输入如三会产生错误，下一步要处理异常。"
    result = asyncio.run(learning.evaluate_submission("project", unit, submission))
    assert result["passed"]
    assert "仅检查提交结构" in result["feedback"]


def test_tutor_graph_changes_strategy_and_uses_history():
    unit = learning._demo_plan("Python", "beginner", 20)[0]
    unit["stage"] = "learn"
    first = asyncio.run(learning.tutor_reply("Python", unit, "我不懂变量", []))
    second = asyncio.run(learning.tutor_reply("Python", unit, "我觉得太简单了", []))
    third = asyncio.run(learning.tutor_reply("Python", unit, "继续", [{"kind": "project", "score": 40}]))
    assert first["mode"] == "demo"
    assert "拆小一步" in first["reply"]
    assert "反例" in second["reply"]
    assert "失败记录" in third["reply"]


def test_text_import_and_safe_errors():
    assert knowledge.extract_document("../资料.MD", b"\xef\xbb\xbf# Python\nvariables") == "# Python\nvariables"
    assert knowledge.extract_document("资料.txt", "变量与数字".encode("gb18030")) == "变量与数字"
    for name, data in (("empty.md", b""), ("program.exe", b"hello"), ("bad.txt", b"binary\x00data"), ("file.pdf", b"bad PDF")):
        with pytest.raises(ValueError):
            knowledge.extract_document(name, data)
    with pytest.raises(ValueError, match="10 MB"):
        knowledge.extract_document("huge.txt", b"x" * (knowledge.MAX_FILE_BYTES + 1))


def test_docx_tables_are_extracted_and_bombs_rejected():
    from docx import Document
    document = Document()
    document.add_paragraph("主文段落")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "输入"
    table.cell(0, 1).text = "结果"
    buffer = io.BytesIO()
    document.save(buffer)
    result = knowledge.extract_document("example.docx", buffer.getvalue())
    assert "主文段落" in result and "输入 | 结果" in result
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "a" * 2_000_000)
    with pytest.raises(ValueError, match="异常压缩"):
        knowledge.extract_document("bomb.docx", bomb.getvalue())


def test_blank_and_encrypted_pdf_are_not_claimed_as_parsed():
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="未提取到文字"):
        knowledge.extract_document("blank.pdf", buffer.getvalue())
    writer.encrypt("secret")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    with pytest.raises(ValueError, match="加密"):
        knowledge.extract_document("private.pdf", encrypted.getvalue())


def test_multilingual_retrieval_is_grounded_and_no_match_is_explicit():
    documents = [
        {"id": 1, "title": "Python变量", "content": "变量保存值。字符串需要用int转换成整数再参与加法。"},
        {"id": 2, "title": "花卉养护", "content": "植物需要适量阳光和水。"},
    ]
    result = asyncio.run(knowledge.answer_question("Python字符串如何转整数？", documents))
    assert [source["id"] for source in result["sources"]] == [1]
    assert "字符串需要用int" in result["answer"]
    empty = asyncio.run(knowledge.answer_question("量子纠缠", documents))
    assert empty["sources"] == [] and "没有找到" in empty["answer"]


def test_provider_status_never_exposes_keys(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")
    assert "test-secret-key" not in json.dumps(providers.provider_status())


@pytest.mark.parametrize("url", ["https://user:secret@example.com/v1", "ftp://example.com/v1", "https://169.254.169.254/v1", "https://metadata.google.internal/v1", "https://api.example.com/v1?token=x"])
def test_provider_rejects_unsafe_configuration(url):
    with pytest.raises(providers.ProviderError):
        providers._endpoint(url)


def test_local_model_endpoint_is_supported():
    assert providers._endpoint("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"
    assert providers._endpoint("http://host.docker.internal:11434/v1") == "http://host.docker.internal:11434/v1/chat/completions"


def _mock_client(monkeypatch, status: int, body: dict):
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers, json):
            return httpx.Response(status, json=body, request=httpx.Request("POST", url))
    monkeypatch.setattr(providers.httpx, "AsyncClient", Client)
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")


def test_configured_ai_failure_does_not_fall_back_to_demo(monkeypatch):
    _mock_client(monkeypatch, 401, {"error": {"message": "test-secret-key"}})
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(learning.generate_plan("Python", "beginner", 20))
    assert "test-secret-key" not in str(error.value)
    assert "拒绝访问" in str(error.value)


def test_model_json_is_validated_and_server_owns_threshold(monkeypatch):
    _mock_client(monkeypatch, 200, {"choices": [{"message": {"content": '{"score": 40, "passed": true, "feedback": "概念存在错误"}'}}]})
    result = asyncio.run(learning.evaluate_submission("teach", {"title": "Python"}, "我的解释"))
    assert result["score"] == 40 and result["passed"] is False
    _mock_client(monkeypatch, 200, {"choices": [{"message": {"content": '{"units": []}'}}]})
    with pytest.raises(providers.ProviderError, match="格式不符合"):
        asyncio.run(learning.generate_plan("Python", "beginner", 20))


def test_model_cannot_invent_document_citations(monkeypatch):
    _mock_client(monkeypatch, 200, {"choices": [{"message": {"content": '{"answer":"引用不存在资料","source_ids":["999"]}'}}]})
    with pytest.raises(providers.ProviderError, match="无法核对"):
        asyncio.run(knowledge.answer_question("Python变量", [{"id": 1, "title": "Python", "content": "变量保存值。"}]))


def test_retrieval_searches_beyond_import_limit_and_handles_english_plurals():
    content = "普通背景。" * 50_000 + "\nUnique variables store a value."
    assert content.index("Unique") > knowledge.MAX_TEXT_CHARS
    sources = knowledge.retrieve("variable", [{"id": "long", "title": "Notes", "content": content}])
    assert len(sources) == 1 and "variables store a value" in sources[0]["excerpt"]


def test_retrieval_chooses_relevant_passage_and_limits_sources():
    documents = [{"id": i, "title": "Python notes", "content": "背景介绍。" * 300 + f"变量保留值，示例{ i }：int将字符串转成整数。"} for i in range(10)]
    sources = knowledge.retrieve("字符串转整数", documents)
    assert len(sources) == 3
    assert len({source["id"] for source in sources}) == 3
    assert all("字符串" in source["excerpt"] for source in sources)


def test_provider_status_invalid_configuration_is_safe(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")
    monkeypatch.setenv("AI_PROVIDER", "unknown")
    status = providers.provider_status()
    assert status["configured"] is False and status["mode"] == "ai"
    assert "尚未就绪" in status["limitations"][0]
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_BASE_URL", "ftp://bad")
    assert providers.provider_status()["configured"] is False


def test_generated_fields_reject_nul_and_fit_database_titles():
    unit = learning._demo_plan("Python", "beginner", 20)[0]
    unit["lesson"]["explanation"] = "有效文字\x00隐藏内容"
    with pytest.raises(ValidationError):
        learning.PlanUnit.model_validate(unit)
    units = learning._demo_plan("长" * 200, "beginner", 20)
    assert all(len(unit["title"]) <= 200 for unit in units)


def test_actual_httpx_transport_sends_valid_provider_request(monkeypatch):
    captured = []
    real_client = httpx.AsyncClient

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"score":85,"passed":true,"feedback":"概念与例子准确，建议补充边界"}'}}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")
    monkeypatch.setenv("AI_MODEL", "local-model")
    monkeypatch.setenv("AI_BASE_URL", "http://host.docker.internal:11434/v1/")
    original = [{"role": "system", "content": "评分"}, {"role": "user", "content": "解释与例子"}]
    result = asyncio.run(providers.complete(original, schema=learning.Assessment))
    assert result["score"] == 85
    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == "http://host.docker.internal:11434/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-secret-key"
    body = json.loads(request.content)
    assert body["model"] == "local-model" and body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system" and body["messages"][-1]["role"] == "user"
    assert "JSON schema" in body["messages"][0]["content"]
    assert original[0]["content"] == "评分"  # Formatting never mutates caller history.


@pytest.mark.parametrize("status", [302, 429, 500])
def test_actual_httpx_errors_are_safe_and_do_not_follow_redirects(monkeypatch, status):
    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"location": "https://other.example/secret"}, json={"error": "test-secret-key"})

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(providers.complete([{"role": "user", "content": "问题"}]))
    assert "test-secret-key" not in str(error.value)
    assert len(requests) == 1


def test_actual_httpx_timeout_and_plain_reply_nul_are_safe(monkeypatch):
    real_client = httpx.AsyncClient

    def timeout(request):
        raise httpx.ReadTimeout("test-secret-key", request=request)

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(timeout), **kwargs))
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")
    with pytest.raises(providers.ProviderError, match="无法连接"):
        asyncio.run(providers.complete([{"role": "user", "content": "问题"}]))
    _mock_client(monkeypatch, 200, {"choices": [{"message": {"content": "有效回复\x00无效字符"}}]})
    with pytest.raises(providers.ProviderError, match="有效内容"):
        asyncio.run(providers.complete([{"role": "user", "content": "问题"}]))
    _mock_client(monkeypatch, 200, {"choices": [{"message": {"content": "回复包含\ud800非法字符"}}]})
    with pytest.raises(providers.ProviderError, match="格式不符合"):
        asyncio.run(providers.complete([{"role": "user", "content": "问题"}]))


def test_ai_provider_http_contract_through_persisted_learning_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    real_client = httpx.AsyncClient
    plan = learning._demo_plan("Python", "beginner", 20)
    captured = []

    def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        user_data = json.loads(payload["messages"][-1]["content"])
        if "daily_minutes" in user_data:
            content = json.dumps({"units": plan}, ensure_ascii=False)
        elif "kind" in user_data:
            content = json.dumps({"score": 85, "passed": True, "feedback": "作品准确，输入与结果可检查；请继续补充无效输入边界。"}, ensure_ascii=False)
        else:
            content = "变量保存值。你可以先预测修改输入后的结果，再实际运行验证。"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "test-secret-key")
    monkeypatch.delenv("REDIS_URL", raising=False)
    application = create_app(f"sqlite:///{tmp_path / 'ai.db'}")
    with TestClient(application) as client:
        goal = client.post("/api/goals", json={"title": "Python", "level": "beginner", "daily_minutes": 20})
        assert goal.status_code == 201
        unit_id = goal.json()["units"][0]["id"]
        unit = client.get(f"/api/units/{unit_id}").json()
        assert "correct_index" not in unit["practice"] and "explanation" not in unit["practice"]
        chat = client.post(f"/api/units/{unit_id}/chat", json={"message": "为什么需要转换输入？"})
        assert chat.status_code == 200 and chat.json()["mode"] == "ai"
        assert client.post(f"/api/units/{unit_id}/learn", json={"reflection": "变量让名字指向值，字符串用于文字，输入要先转换为整数才能进行数值计算。"}).status_code == 200
        assert client.post(f"/api/units/{unit_id}/practice", json={"answer": "1"}).json()["passed"] is True
        project = client.post(f"/api/units/{unit_id}/project", json={"content": "使用price和count变量计算购物总价，输入12和3得到36，数量0这个边界得到0，与预期一致。"})
        assert project.status_code == 200
        assert project.json()["unit"]["stage"] == "teach" and project.json()["score"] == 85
        sessions = client.get(f"/api/units/{unit_id}").json()["sessions"]
        assert [item["kind"] for item in sessions] == ["chat", "learn", "practice", "project"]
    assert len(captured) == 3
    tutor_input = json.loads(captured[1]["messages"][-1]["content"])
    assert "practice" not in tutor_input["unit"]
    assert "test-secret-key" not in json.dumps(goal.json())


def test_invalid_ai_plan_fails_api_without_persisting_goal(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    _mock_client(monkeypatch, 200, {"choices": [{"message": {"content": '{"units":[]}'}}]})
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(create_app(f"sqlite:///{tmp_path / 'invalid.db'}")) as client:
        response = client.post("/api/goals", json={"title": "Python"})
        assert response.status_code == 502 and "格式不符合" in response.json()["detail"]
        assert client.get("/api/goals").json() == []
