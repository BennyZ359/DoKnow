"""Memory service (whitepaper §12) — the three-layer learner memory.

- Global Memory (LearnerMemory): durable facts about the learner across goals.
- Course Memory (CourseMemory): per-course context the teaching agent needs.
- Learning Events (LearningEvent): append-only observations — the feed the AI
  Learning Manager's Observe step reasons over.

Every memory write carries a ``source`` (USER_INPUT / SYSTEM_FACT /
AI_ASSESSMENT / AI_GUESS) and a ``confidence``. Writes are versioned, not
destructive: a losing candidate is skipped, a winning candidate deactivates
the old row and inserts a new one. An ``AI_GUESS`` can never overwrite
anything the learner actually stated (§12 precedence rules).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.events import utcnow
from app.models.memory import CourseMemory, EventSource, LearnerMemory, LearningEvent, MemoryType

logger = structlog.get_logger("app.services.memory")

# Precedence rank for memory sources (§12): higher wins.
SOURCE_RANK: dict[str, int] = {
    EventSource.USER_INPUT.value: 4,
    EventSource.SYSTEM_FACT.value: 3,
    EventSource.AI_ASSESSMENT.value: 2,
    EventSource.AI_GUESS.value: 1,
}


# ---------------------------------------------------------------------------
# Learning events (append-only)
# ---------------------------------------------------------------------------


def record_event(
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID | None,
    subject_type: str,
    subject_id: uuid.UUID | None,
    event_name: str,
    payload: dict | None = None,
    correlation_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Append one observation. Events are never edited (audit trail, §12)."""
    with SessionLocal() as db:
        event = LearningEvent(
            user_id=user_id,
            goal_id=goal_id,
            subject_type=subject_type,
            subject_id=subject_id,
            event_name=event_name,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        db.add(event)
        db.commit()
        return event.id


def recent_events(
    user_id: uuid.UUID,
    *,
    goal_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """Most recent events, newest first — the Observe feed (§7)."""
    with SessionLocal() as db:
        stmt = (
            select(LearningEvent)
            .where(LearningEvent.user_id == user_id)
            .order_by(LearningEvent.occurred_at.desc())
            .limit(limit)
        )
        if goal_id is not None:
            stmt = stmt.where(LearningEvent.goal_id == goal_id)
        rows = db.scalars(stmt).all()
        return [
            {
                "id": e.id,
                "goal_id": e.goal_id,
                "subject_type": e.subject_type,
                "subject_id": e.subject_id,
                "event_name": e.event_name,
                "payload": e.payload or {},
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
            }
            for e in rows
        ]


def has_recent_event(
    user_id: uuid.UUID,
    *,
    event_name: str,
    hours: int = 24,
    goal_id: uuid.UUID | None = None,
    payload_key: str | None = None,
    payload_value: str | None = None,
) -> bool:
    """Dedupe helper: has this event already fired within ``hours``?

    Used by the intervention service to avoid nagging the learner with the
    same message for the same problem twice in a row (§7 "不要动作轰炸").
    """
    cutoff = utcnow() - timedelta(hours=hours)
    with SessionLocal() as db:
        stmt = select(LearningEvent.id).where(
            LearningEvent.user_id == user_id,
            LearningEvent.event_name == event_name,
            LearningEvent.occurred_at >= cutoff,
        )
        if goal_id is not None:
            stmt = stmt.where(LearningEvent.goal_id == goal_id)
        if payload_key is not None:
            stmt = stmt.where(LearningEvent.payload[payload_key].astext == payload_value)
        return db.scalar(stmt.limit(1)) is not None


# ---------------------------------------------------------------------------
# Global memory (LearnerMemory)
# ---------------------------------------------------------------------------


def upsert_memory(
    *,
    user_id: uuid.UUID,
    memory_type: str,
    key: str,
    value: dict,
    source: str,
    confidence: float,
    scope: str = "GLOBAL",
) -> dict:
    """Write one memory entry under the precedence rules.

    A candidate wins only if its source rank (or equal rank with ≥
    confidence) beats the active incumbent; losing candidates are skipped
    and logged. Winning writes deactivate the old row (history kept) and
    insert a new one.
    """
    source = EventSource(source).value
    with SessionLocal() as db:
        incumbent = db.scalar(
            select(LearnerMemory).where(
                LearnerMemory.user_id == user_id,
                LearnerMemory.key == key,
                LearnerMemory.is_active.is_(True),
            )
        )
        if incumbent is not None and not _wins(source, confidence, incumbent):
            logger.debug(
                "memory.write_skipped",
                key=key,
                new_source=source,
                new_confidence=confidence,
                incumbent_source=incumbent.source.value if incumbent.source else None,
                incumbent_confidence=incumbent.confidence,
            )
            return {"accepted": False, "reason": "precedence"}

        if incumbent is not None:
            incumbent.is_active = False
        entry = LearnerMemory(
            user_id=user_id,
            memory_type=MemoryType(memory_type),
            key=key,
            value=value,
            source=EventSource(source),
            confidence=confidence,
            scope=scope,
            meta={"superseded": str(incumbent.id)} if incumbent is not None else {},
        )
        db.add(entry)
        db.commit()
        logger.info("memory.upserted", key=key, source=source, confidence=confidence)
        return {"accepted": True, "id": str(entry.id)}


def list_memories(user_id: uuid.UUID, *, types: list[str] | None = None) -> list[dict]:
    """Active global memories — the learner profile the AI adapts to."""
    with SessionLocal() as db:
        stmt = (
            select(LearnerMemory)
            .where(LearnerMemory.user_id == user_id, LearnerMemory.is_active.is_(True))
            .order_by(LearnerMemory.confidence.desc())
        )
        if types:
            stmt = stmt.where(LearnerMemory.memory_type.in_([MemoryType(t) for t in types]))
        return [_memory_to_dict(m) for m in db.scalars(stmt).all()]


# ---------------------------------------------------------------------------
# Course memory
# ---------------------------------------------------------------------------


def upsert_course_memory(
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    memory_type: str,
    key: str,
    value: dict,
    source: str,
    confidence: float,
) -> dict:
    """Same precedence rules, scoped to one course (§12 Course Memory)."""
    source = EventSource(source).value
    with SessionLocal() as db:
        incumbent = db.scalar(
            select(CourseMemory).where(
                CourseMemory.user_id == user_id,
                CourseMemory.course_id == course_id,
                CourseMemory.key == key,
                CourseMemory.is_active.is_(True),
            )
        )
        if incumbent is not None and not _wins(source, confidence, incumbent):
            return {"accepted": False, "reason": "precedence"}
        if incumbent is not None:
            incumbent.is_active = False
        entry = CourseMemory(
            user_id=user_id,
            course_id=course_id,
            memory_type=MemoryType(memory_type),
            key=key,
            value=value,
            source=EventSource(source),
            confidence=confidence,
        )
        db.add(entry)
        db.commit()
        return {"accepted": True, "id": str(entry.id)}


def list_course_memories(user_id: uuid.UUID, course_id: uuid.UUID) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(CourseMemory).where(
                CourseMemory.user_id == user_id,
                CourseMemory.course_id == course_id,
                CourseMemory.is_active.is_(True),
            )
        ).all()
        return [_memory_to_dict(m) for m in rows]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _wins(new_source: str, new_confidence: float, incumbent) -> bool:
    """Precedence decision (§12): rank first, confidence breaks ties."""
    if SOURCE_RANK[new_source] > SOURCE_RANK[incumbent.source.value]:
        return True
    if SOURCE_RANK[new_source] == SOURCE_RANK[incumbent.source.value]:
        return new_confidence >= incumbent.confidence
    return False


def _memory_to_dict(m) -> dict:
    return {
        "id": m.id,
        "memory_type": m.memory_type.value if m.memory_type else None,
        "key": m.key,
        "value": m.value or {},
        "source": m.source.value if m.source else None,
        "confidence": m.confidence,
        "scope": getattr(m, "scope", "GLOBAL"),
    }
