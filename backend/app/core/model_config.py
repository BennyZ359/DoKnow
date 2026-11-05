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
    """Merge an override into the stored one and persist it.

    Only non-empty values are applied, so a masked-key edit (user changes the
    model but leaves the API-key field blank) never wipes the stored key. Use
    :func:`clear_llm_override` to reset entirely. Returns the stored dict.
    """
    current = get_llm_override()
    for key in _FIELDS:
        value = fields.get(key)
        if value and str(value).strip():
            current[key] = str(value).strip()
    get_redis().set(_KEY, json.dumps(current, ensure_ascii=False))
    logger.info("model_config.set", fields=sorted(current.keys()))
    return current


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
