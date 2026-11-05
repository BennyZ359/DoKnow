"""Global LLM override — lets the user point the whole app at any
OpenAI-compatible model (their own key / base URL / model) without redeploying.

Stored in Redis (not the DB) because it is instance configuration, not domain
data, and must be readable from background agent runs (which have no request
context). When absent, every LLM call falls back to the env-based defaults.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

from app.core.redis import get_redis

logger = structlog.get_logger("app.core.model_config")

_KEY = "doknow:llm:override"

# Fields we persist for an override. `provider` is cosmetic (drives UI presets);
# the client only needs base_url / api_key / model.
_FIELDS = ("provider", "base_url", "api_key", "model")


def get_llm_override() -> dict[str, str]:
    """Effective LLM override as a dict of the supported fields (empty if unset)."""
    try:
        raw = get_redis().get(_KEY)
    except Exception as exc:  # redis down → fall back to env defaults
        logger.warning("model_config.read_failed", error=str(exc)[:200])
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return {k: str(data[k]) for k in _FIELDS if data.get(k)}


def set_llm_override(**fields: str | None) -> dict[str, str]:
    """Persist an override. ``None``/empty values are dropped. Returns stored dict."""
    payload: dict[str, str] = {}
    for key in _FIELDS:
        value = fields.get(key)
        if value:
            payload[key] = str(value).strip()
    get_redis().set(_KEY, json.dumps(payload, ensure_ascii=False))
    logger.info("model_config.set", fields=sorted(payload.keys()))
    return payload


def clear_llm_override() -> None:
    """Remove any override so calls fall back to env defaults."""
    get_redis().delete(_KEY)
    logger.info("model_config.cleared")


def masked_override() -> dict[str, Any]:
    """Override safe to return to the UI — API key reduced to a hint."""
    override = get_llm_override()
    if not override:
        return {"configured": False, "fields": {}}
    key = override.get("api_key", "")
    hint = (key[:4] + "…" + key[-4:]) if len(key) > 8 else "••••"
    fields = {**override, "api_key_hint": hint}
    fields.pop("api_key", None)
    return {"configured": True, "fields": fields}
