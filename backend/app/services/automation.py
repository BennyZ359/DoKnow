"""Event-driven automation (whitepaper §11) — the system's reflexes.

Domain events on the in-process bus are mapped to agent runs:

- LEARNING_GOAL_CREATED    → build the knowledge system (§5.2)
- KNOWLEDGE_SYSTEM_BUILT    → generate the learning path (§5.3)
- LEARNING_PATH_GENERATED   → generate the first course (§5.4)
- TASK_COMPLETED / REVIEW_DUE / WEAKNESS_DETECTED → one Learning Manager
  cycle, throttled to at most one run per goal per hour

Every trigger is guarded twice: a Redis lock dedupes event storms, and each
workflow has its own idempotency guard (skip when the artifact exists), so
automation can never spam the LLM or duplicate business state. Handlers run
in daemon threads — publishers (HTTP requests) never block on agent runs.

The scheduler (app.main) complements this with time-based triggers: marking
reviews due, expiring tasks, and periodic manager cycles for idle goals.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

import structlog

from app.agents import workflows
from app.core.events import DomainEvent, EventType, bus
from app.core.redis import get_cache
from app.services import goal_service

log = structlog.get_logger("app.services.automation")

MANAGER_CYCLE_THROTTLE_SECONDS = 3600
TRIGGER_LOCK_SECONDS = 1800


def _lock(key: str, ttl: int) -> bool:
    """Redis dedupe; if Redis is down we proceed (workflow guards still hold)."""
    try:
        return get_cache().acquire_lock(key, ttl=ttl)
    except Exception:
        return True


def _spawn(target, *args: Any) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="doknow-automation").start()


def _goal_owner(goal_id: uuid.UUID) -> uuid.UUID | None:
    goal = goal_service.get_goal_internal(goal_id)
    return uuid.UUID(goal["user_id"]) if goal else None


# ---------------------------------------------------------------------------
# Pipeline chain: goal → knowledge → path → course
# ---------------------------------------------------------------------------


def _build_knowledge(goal_id: uuid.UUID, user_id: uuid.UUID) -> None:
    result = workflows.build_knowledge_system(goal_id, user_id)
    log.info("automation.knowledge_built", goal_id=str(goal_id), status=result.status.value)


def _on_goal_created(event: DomainEvent) -> None:
    goal_id = uuid.UUID(str(event.aggregate_id))
    user_id = _goal_owner(goal_id)
    if user_id is None:
        return
    if not _lock(f"trigger:knowledge:{goal_id}", TRIGGER_LOCK_SECONDS):
        return
    _spawn(_build_knowledge, goal_id, user_id)


def _on_knowledge_built(event: DomainEvent) -> None:
    goal_id = uuid.UUID(str(event.aggregate_id))
    user_id = _goal_owner(goal_id)
    if user_id is None:
        return
    if not _lock(f"trigger:path:{goal_id}", TRIGGER_LOCK_SECONDS):
        return
    _spawn(workflows.generate_learning_path, goal_id, user_id)


def _on_path_generated(event: DomainEvent) -> None:
    goal_id_raw = (event.payload or {}).get("goal_id") or event.aggregate_id
    goal_id = uuid.UUID(str(goal_id_raw))
    user_id = _goal_owner(goal_id)
    if user_id is None:
        return
    if not _lock(f"trigger:course:{goal_id}", TRIGGER_LOCK_SECONDS):
        return
    _spawn(workflows.generate_course, goal_id, user_id)


# ---------------------------------------------------------------------------
# Proactive loop triggers (§7) — throttled
# ---------------------------------------------------------------------------


def _run_manager_cycle(goal_id: uuid.UUID, user_id: uuid.UUID, trigger: str) -> None:
    goal = goal_service.get_goal_internal(goal_id)
    if not goal or goal.get("status") != "ACTIVE":
        return
    result = workflows.run_manager_cycle(goal_id, user_id)
    log.info(
        "automation.manager_cycle_done",
        goal_id=str(goal_id),
        trigger=trigger,
        status=result.status.value,
    )


def _maybe_manager_cycle(goal_id: uuid.UUID, trigger: str) -> None:
    user_id = _goal_owner(goal_id)
    if user_id is None:
        return
    # Throttle: at most one manager cycle per goal per hour, whatever fires.
    if not _lock(f"trigger:manager:{goal_id}", MANAGER_CYCLE_THROTTLE_SECONDS):
        return
    _spawn(_run_manager_cycle, goal_id, user_id, trigger)


def _on_task_completed(event: DomainEvent) -> None:
    _maybe_manager_cycle(uuid.UUID(str(event.aggregate_id)), "task_completed")


def _on_review_due(event: DomainEvent) -> None:
    _maybe_manager_cycle(uuid.UUID(str(event.aggregate_id)), "review_due")


def _on_weakness_detected(event: DomainEvent) -> None:
    _maybe_manager_cycle(uuid.UUID(str(event.aggregate_id)), "weakness_detected")


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


_installed = False


def install_event_handlers() -> None:
    """Subscribe automation to the bus. Idempotent (import-safe)."""
    global _installed
    if _installed:
        return
    bus.subscribe(EventType.LEARNING_GOAL_CREATED, _on_goal_created)
    bus.subscribe(EventType.KNOWLEDGE_SYSTEM_BUILT, _on_knowledge_built)
    bus.subscribe(EventType.LEARNING_PATH_GENERATED, _on_path_generated)
    bus.subscribe(EventType.TASK_COMPLETED, _on_task_completed)
    bus.subscribe(EventType.REVIEW_DUE, _on_review_due)
    bus.subscribe(EventType.WEAKNESS_DETECTED, _on_weakness_detected)
    _installed = True
    log.info("automation.handlers_installed")
