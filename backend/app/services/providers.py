"""A small, explicit OpenAI-compatible boundary; credentials never leave here."""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError


class ProviderError(RuntimeError):
    """A safe error suitable for displaying to a learner."""


def configuration() -> dict:
    provider = os.getenv("AI_PROVIDER", "demo").strip().lower()
    return {
        "provider": provider,
        "model": os.getenv("AI_MODEL", "gpt-4.1-mini").strip(),
        "key": os.getenv("AI_API_KEY", "").strip(),
        "base_url": os.getenv("AI_BASE_URL", "https://api.openai.com/v1").strip(),
    }


def provider_status() -> dict:
    config = configuration()
    demo = config["provider"] == "demo"
    configured = demo or bool(config["provider"] in {"openai", "compatible"} and config["key"] and config["model"])
    if not demo and configured:
        try:
            _endpoint(config["base_url"])
        except ProviderError:
            configured = False
    limitations = [
        "当前为体验模式：课程来自示范模板，提交仅做结构检查，不能证明知识正确或真正掌握。",
        "体验模式的资料问答返回检索摘录；配置 AI 后可获得基于材料的解释。",
    ] if demo else [
        "AI 评估可能出错；请用实际结果和可靠资料核验结论。",
        "配置的模型服务会收到学习目标、提交内容及资料问答相关摘录。",
    ]
    if not configured:
        limitations.insert(0, "模型配置尚未就绪，请检查 AI_PROVIDER、AI_BASE_URL、AI_API_KEY 和 AI_MODEL；本次不会自动切换为体验结果。")
    return {
        "mode": "demo" if demo else "ai",
        "provider": config["provider"],
        "model": "离线体验课程" if demo else config["model"],
        "configured": configured,
        "limitations": limitations,
    }


def _endpoint(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise ProviderError("模型服务地址格式无效，请检查 AI_BASE_URL。") from exc
    if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError("模型服务地址须为不含凭据、参数或片段的 API 基础地址。")
    # The endpoint comes exclusively from operator-controlled environment, never
    # request data. HTTP also supports LAN/Docker model servers such as Ollama.
    if parsed.scheme not in {"http", "https"}:
        raise ProviderError("模型服务地址须使用 HTTP 或 HTTPS。")
    if host.startswith("169.254.") or host in {"metadata.google.internal", "0.0.0.0"} or host.startswith("fe80:"):
        raise ProviderError("模型服务地址不能指向元数据或链路本地地址。")
    if port == 0:
        raise ProviderError("模型服务端口无效。")
    return base_url.rstrip("/") + "/chat/completions"


async def complete(messages: list[dict], *, schema: type[BaseModel] | None = None) -> str | dict:
    config = configuration()
    if config["provider"] not in {"openai", "compatible"}:
        raise ProviderError("AI_PROVIDER 需设置为 demo、openai 或 compatible。")
    if not config["key"] or not config["model"]:
        raise ProviderError("模型服务尚未配置：请设置 AI_API_KEY 和 AI_MODEL，或使用 demo 模式。")
    endpoint = _endpoint(config["base_url"])
    payload: dict = {"model": config["model"], "messages": messages, "temperature": 0.3, "max_tokens": 5000}
    if schema:
        payload["response_format"] = {"type": "json_object"}
        formatted = [dict(message) for message in messages]
        instruction = "仅输出符合此 JSON schema 的 JSON 对象：" + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        if formatted and formatted[0].get("role") == "system":
            formatted[0]["content"] += "\n\n" + instruction
        else:
            formatted.insert(0, {"role": "system", "content": instruction})
        payload["messages"] = formatted
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=False, trust_env=False) as client:
            response = await client.post(endpoint, headers={"Authorization": f"Bearer {config['key']}"}, json=payload)
        if response.status_code in {401, 403}:
            raise ProviderError("模型服务拒绝访问，请检查 API 密钥及模型权限。")
        if response.status_code == 429:
            raise ProviderError("模型服务当前限流或额度不足，请稍后重试。")
        if response.status_code >= 400 or response.is_redirect:
            raise ProviderError("模型服务请求失败，请检查服务地址与模型配置。")
        if len(response.content) > 2_000_000:
            raise ProviderError("模型返回内容过大，请更换模型或重试。")
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip() or "\x00" in content:
            raise ProviderError("模型没有返回有效内容，请重试。")
        # JSON permits escaped surrogate code points; UTF-8 persistence and API
        # serialization do not. Fail before any learner evidence is recorded.
        content.encode("utf-8")
        if schema:
            return schema.model_validate_json(content).model_dump()
        return content.strip()
    except ProviderError:
        raise
    except (httpx.HTTPError, TimeoutError) as exc:
        raise ProviderError("暂时无法连接模型服务，请检查网络后重试。") from exc
    except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
        raise ProviderError("模型返回格式不符合要求，本次操作未生效，请重试。") from exc
