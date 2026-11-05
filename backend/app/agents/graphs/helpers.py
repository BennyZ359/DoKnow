"""Shared helpers for graph nodes: prompt-safe JSON digests.

LLM context windows are finite and prompts must stay focused, so every
snapshot handed to a prompt goes through a deterministic digest step:
compact JSON, truncated with an explicit marker. Facts are never rewritten
on the way — only shortened.
"""

from __future__ import annotations

import json
from typing import Any


def digest(value: Any, limit: int = 4000) -> str:
    """Compact JSON for prompts, truncated with an explicit marker."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "…(已截断)"


def digest_tasks(tasks: list[dict], limit: int = 3000) -> str:
    """Compact task list: only the fields the diagnosis reasons over."""
    slim = [
        {
            k: t.get(k)
            for k in ("title", "task_type", "status", "due_at", "scheduled_for", "completed_at")
        }
        for t in (tasks or [])
    ]
    return digest(slim, limit)


def digest_events(events: list[dict], limit: int = 3000) -> str:
    """Compact event stream for prompts (event name, time, small payload)."""
    slim = [
        {
            "name": e.get("event_name"),
            "at": e.get("occurred_at"),
            "payload": digest(e.get("payload") or {}, 200),
        }
        for e in (events or [])
    ]
    return digest(slim, limit)


def digest_mastery(mastery: dict, limit: int = 2500) -> str:
    """Mastery snapshot: {kp_id: {state, score}} flattened for prompts."""
    slim = {
        k: {"state": v.get("mastery_state"), "score": v.get("score")}
        for k, v in (mastery or {}).items()
    }
    return digest(slim, limit)


def digest_points(points: list[dict], limit: int = 2500) -> str:
    """Knowledge points for prompts: code/name/type/difficulty/prerequisites."""
    slim = [
        {
            "code": p.get("code"),
            "name": p.get("name"),
            "description": digest(p.get("description") or "", 120),
            "type": p.get("knowledge_type"),
            "difficulty": p.get("difficulty"),
            "methods": p.get("recommended_methods"),
            "est_minutes": p.get("est_minutes"),
            "prerequisites": p.get("prerequisites") or [],
        }
        for p in (points or [])
    ]
    return digest(slim, limit)


def digest_memories(memories: list[dict], limit: int = 1500) -> str:
    slim = [
        {
            "key": m.get("key"),
            "value": m.get("value"),
            "source": m.get("source"),
            "confidence": m.get("confidence"),
        }
        for m in (memories or [])
    ]
    return digest(slim, limit)


__all__ = [
    "digest",
    "digest_events",
    "digest_mastery",
    "digest_memories",
    "digest_points",
    "digest_tasks",
]
