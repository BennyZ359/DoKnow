"""Instance settings API — currently the global LLM model override.

Lets the user point the whole app at any OpenAI-compatible model (their own
key / base URL / model) from the UI. Stored in Redis so background agent runs
pick it up too; when unset, LLM calls fall back to env defaults.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.model_config import clear_llm_override, masked_override, set_llm_override

router = APIRouter(prefix="/settings", tags=["settings"])


class LlmOverrideRequest(BaseModel):
    """Generic OpenAI-compatible model config. Empty strings clear that field."""

    provider: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)


def _ok(**extra: Any) -> dict[str, Any]:
    return {"ok": True, **extra}


@router.get("/llm")
def get_llm_settings(user_id: CurrentUser) -> dict[str, Any]:
    """Current model override (API key masked) + whether one is configured."""
    return _ok(**masked_override())


@router.put("/llm")
def update_llm_settings(body: LlmOverrideRequest, user_id: CurrentUser) -> dict[str, Any]:
    """Set the model override. All fields optional; blanks are dropped."""
    stored = set_llm_override(
        provider=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
    )
    if not stored:
        clear_llm_override()
    return _ok(**masked_override())


@router.delete("/llm")
def reset_llm_settings(user_id: CurrentUser) -> dict[str, Any]:
    """Clear the override so LLM calls fall back to env defaults."""
    clear_llm_override()
    return _ok(configured=False, fields={})
