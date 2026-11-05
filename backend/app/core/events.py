"""Event bus primitives for event-driven automation.

The whitepaper (§11) requires an event-driven + scheduled automation model:
business services publish domain events (e.g. ``task_completed``,
``mastery_changed``, ``course_quality_issue``); automation subscribers react
by dispatching agent runs, sending notifications, or enqueuing review tasks.

This module provides the *contracts only* — the in-process bus is a simple
synchronous dispatcher. A production deployment would back this with Redis
Streams / a job queue; the interface is kept stable so the transport can
change without touching callers.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[["DomainEvent"], None]


def utcnow() -> datetime:
    return datetime.now(UTC)


class EventType(StrEnum):
    """Canonical domain event types (§11 automation triggers)."""

    LEARNING_GOAL_CREATED = "learning_goal.created"
    LEARNING_GOAL_UPDATED = "learning_goal.updated"
    KNOWLEDGE_SYSTEM_BUILT = "knowledge_system.built"
    LEARNING_PATH_GENERATED = "learning_path.generated"
    COURSE_GENERATED = "course.generated"
    COURSE_QUALITY_ISSUE = "course.quality_issue"
    LESSON_STARTED = "lesson.started"
    TASK_COMPLETED = "task.completed"
    EXERCISE_ATTEMPTED = "exercise.attempted"
    MASTERY_CHANGED = "mastery.changed"
    WEAKNESS_DETECTED = "weakness.detected"
    REVIEW_DUE = "review.due"
    INTERVENTION_TRIGGERED = "intervention.triggered"


@dataclass
class DomainEvent:
    """A domain event payload."""

    type: EventType
    aggregate_id: str
    aggregate_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: datetime = field(default_factory=utcnow)
    correlation_id: str | None = None
    causation_id: str | None = None


class EventBus:
    """In-process synchronous event dispatcher.

    Handlers are registered by event type. A handler may raise; failures are
    logged and isolated so one bad handler does not break the publisher.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(
        self,
        type_: EventType | str,
        *,
        aggregate_id: Any,
        aggregate_type: str,
        payload: dict[str, Any] | None = None,
    ) -> DomainEvent:
        """Publish one event and dispatch to handlers synchronously.

        Handler failures are logged and isolated — a bad subscriber never
        breaks the publisher (the business mutation already succeeded).
        """
        event = DomainEvent(
            type=EventType(type_),  # type: ignore[arg-type]
            aggregate_id=str(aggregate_id),
            aggregate_type=aggregate_type,
            payload=payload or {},
        )
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler failed for %s", event.type)
        return event


bus = EventBus()
