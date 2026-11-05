"""LLM provider abstraction — the only door to model capabilities.

Provider-agnostic by design: any OpenAI-compatible endpoint works (OpenAI,
GLM, DeepSeek, Moonshot, vLLM, Ollama, ...) just by setting ``LLM_BASE_URL``
and ``LLM_MODEL`` in configuration. Every AI-side component (agent graphs,
content quality checks, memory inference) must go through this client so that:

- the model / provider can be swapped via configuration only;
- token usage is measured in one place (per-call and aggregate);
- tests substitute a deterministic fake instead of a live API.

Structured output: ``chat_json`` enforces JSON mode where the endpoint supports
it, strips markdown fences, parses defensively (outermost JSON value), and can
validate the result against a pydantic model — retrying once with the parse
error appended so the model can self-correct.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, ClassVar, TypeVar

import structlog
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = structlog.get_logger("app.agents.llm")

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$")


class LLMError(RuntimeError):
    """Base error for LLM access failures."""


class LLMNotConfiguredError(LLMError):
    """Raised when a call is attempted without LLM_API_KEY."""


class LLMJsonParseError(LLMError):
    """Raised when the model output cannot be parsed as JSON after retries."""


@dataclass(slots=True)
class LLMUsage:
    """Token accounting for a single call (feeding AgentRun cost columns)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class LLMResult:
    """A completed chat call: text content plus measured usage."""

    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    model: str = ""


def extract_json(text: str) -> Any:
    """Parse the outermost JSON value from a model reply.

    Tolerates markdown fences and prose wrapped around the JSON payload.
    Raises ``json.JSONDecodeError`` when nothing parseable is found.
    """
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost {...} / [...] slice.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
    raise json.JSONDecodeError("no JSON object or array found", cleaned, 0)


class LLMClient:
    """OpenAI-compatible chat + embeddings client.

    Transient errors (rate limit, timeout, connection, 5xx) are retried by
    the SDK's built-in backoff; JSON parse failures are retried by
    ``chat_json`` with the error fed back to the model.
    """

    # Retried by the OpenAI SDK's own exponential backoff (default 2 retries).
    _TRANSIENT: ClassVar[tuple[type[Exception], ...]] = (
        RateLimitError,
        APITimeoutError,
        APIConnectionError,
        InternalServerError,
    )

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        embedding_model: str | None = None,
        usage_callback: Callable[[LLMUsage], None] | None = None,
    ) -> None:
        self._model = model or settings.llm_model
        self._embedding_model = embedding_model or settings.embedding_model
        self._api_key = api_key or settings.llm_api_key or ""
        self._base_url = base_url or settings.llm_base_url or None
        self._usage_callback = usage_callback
        self._client: OpenAI | None = None

    @property
    def model(self) -> str:
        return self._model

    def _ensure_client(self) -> OpenAI:
        if self._client is None:
            if not self._api_key:
                raise LLMNotConfiguredError(
                    "LLM_API_KEY is not configured; set it in .env to enable AI features"
                )
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                max_retries=2,
                timeout=settings.agent_timeout_seconds,
            )
        return self._client

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResult:
        """One chat completion. Returns content + measured token usage."""
        payload: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
        payload.extend(messages)
        request: dict[str, Any] = {
            "model": self._model,
            "messages": payload,
            "temperature": temperature,
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        try:
            response = self._ensure_client().chat.completions.create(**request)
        except Exception as exc:
            # Some endpoints reject response_format; retry once without it.
            if json_mode and not isinstance(exc, self._TRANSIENT) and "response_format" in str(exc):
                request.pop("response_format", None)
                response = self._ensure_client().chat.completions.create(**request)
            else:
                raise
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        llm_usage = LLMUsage(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        if self._usage_callback is not None:
            self._usage_callback(llm_usage)
        return LLMResult(
            content=(choice.message.content or "").strip(),
            usage=llm_usage,
            model=response.model or self._model,
        )

    # -------------------------------------------------------------- chat_json
    def chat_json(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_model: type[T] | None = None,
        schema_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Chat expecting a JSON reply; parse defensively and self-correct once.

        ``schema_hint`` describes the expected shape in the prompt; when
        ``response_model`` (a pydantic class) is given, the parsed JSON is
        validated through it and returned as ``model_dump``-style dict/list.
        """
        request = list(messages)
        if schema_hint is not None:
            request.append(
                {
                    "role": "system",
                    "content": (
                        "严格只输出一个合法的 JSON 对象，不要输出任何解释或 Markdown 代码块。"
                        f"JSON 必须符合以下结构约定：{json.dumps(schema_hint, ensure_ascii=False)}"
                    ),
                }
            )
        prompt_tokens = completion_tokens = 0
        last_error: Exception | None = None
        text = ""
        for attempt in (1, 2):
            result = self.chat(
                request,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            prompt_tokens += result.usage.prompt_tokens
            completion_tokens += result.usage.completion_tokens
            text = result.content
            try:
                parsed = extract_json(text)
                if response_model is not None:
                    parsed = response_model.model_validate(parsed).model_dump(mode="json")
                logger.debug(
                    "llm.json_parsed",
                    attempt=attempt,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                # Attach measured usage to the (plain) dict for cost tracking.
                if isinstance(parsed, dict):
                    parsed["_usage"] = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    }
                return parsed
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.warning("llm.json_retry", attempt=attempt, error=str(exc)[:300])
                # Feed the failure back so the model can self-correct.
                request = request + [
                    {"role": "assistant", "content": text[:2000]},
                    {
                        "role": "user",
                        "content": (
                            f"上一次输出不是合法 JSON 或不符合结构要求（错误：{str(exc)[:300]}）。"
                            "请重新输出，仅输出 JSON 本身。"
                        ),
                    },
                ]
        raise LLMJsonParseError(f"model did not return valid JSON after retry: {last_error}")

    # ------------------------------------------------------------------ embed
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts with the configured embedding model."""
        if not texts:
            return []
        response = self._ensure_client().embeddings.create(
            model=self._embedding_model,
            input=list(texts),
        )
        emb_usage = getattr(response, "usage", None)
        if self._usage_callback is not None and emb_usage is not None:
            self._usage_callback(
                LLMUsage(prompt_tokens=getattr(emb_usage, "prompt_tokens", 0) or 0)
            )
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


@lru_cache
def get_llm() -> LLMClient:
    """Process-wide client singleton."""
    return LLMClient()
