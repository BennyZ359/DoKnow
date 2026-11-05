"""Review service (whitepaper §13.2 module 9) — the 温 of 学练用讲温.

Spaced repetition over mastery: Ebbinghaus-style intervals advance on success
and reset on failure. Scheduling is idempotent — the manager loop and the
assessment state machine can both call ``schedule_review`` freely; at most one
uncompleted review exists per (user, knowledge point) at a time.

``mark_due`` flips PENDING reviews whose time has come to DUE and emits the
REVIEW_DUE event the scheduler/manager loop listens to (§11).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.events import EventType, bus, utcnow
from app.models.assessment import ReviewStatus, ReviewTask, ReviewType
from app.services import memory_service

logger = structlog.get_logger("app.services.review")

# Ebbinghaus-style expanding intervals (§9), in days.
EBBINGHAUS_DAYS = [1, 2, 4, 7, 15, 30]


class ReviewServiceError(Exception):
    pass


class ReviewNotFoundError(ReviewServiceError):
    pass


class NotOwnerError(ReviewServiceError):
    pass


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def schedule_review(
    *,
    user_id: uuid.UUID,
    knowledge_point_id: uuid.UUID,
    review_type: str = "SPACED",
    reason: str | None = None,
    due_in_days: int | None = None,
) -> dict:
    """Idempotently ensure an uncompleted review exists for the point.

    Returns {"id", "created", "due_at"}. An existing PENDING/DUE review is
    returned as-is (its schedule may only be pulled earlier explicitly via
    ``due_in_days``).
    """
    rtype = ReviewType(review_type)
    with SessionLocal() as db:
        existing = db.scalar(
            select(ReviewTask).where(
                ReviewTask.user_id == user_id,
                ReviewTask.knowledge_point_id == knowledge_point_id,
                ReviewTask.status.in_([ReviewStatus.PENDING, ReviewStatus.DUE]),
            )
        )
        if existing is not None:
            if due_in_days is not None:
                new_due = utcnow() + timedelta(days=due_in_days)
                if existing.due_at is None or new_due < existing.due_at:
                    existing.due_at = new_due
                    db.commit()
            return {"id": str(existing.id), "created": False, "due_at": existing.due_at}

        interval_days = due_in_days if due_in_days is not None else EBBINGHAUS_DAYS[0]
        task = ReviewTask(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
            review_type=rtype,
            status=ReviewStatus.PENDING,
            due_at=utcnow() + timedelta(days=interval_days),
            interval_days=interval_days,
            schedule={"intervals": EBBINGHAUS_DAYS, "index": 0},
            result={"reason": reason} if reason else {},
        )
        db.add(task)
        db.commit()
        logger.info(
            "review.scheduled",
            user_id=str(user_id),
            kp=str(knowledge_point_id),
            review_type=rtype.value,
        )
        return {"id": str(task.id), "created": True, "due_at": task.due_at}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def complete_review(
    *,
    user_id: uuid.UUID,
    review_id: uuid.UUID,
    score: float,
    confidence: float = 0.8,
) -> dict:
    """Complete a review: fold the outcome into mastery and advance the schedule.

    Pass (score ≥ 0.5) → interval index advances; fail → index resets to 0
    and the next review comes in 1 day (§9 weakness reinforcement).
    """
    # Lazy import: assessment_service schedules reviews on its updates.
    from app.services import assessment_service

    with SessionLocal() as db:
        task = db.get(ReviewTask, review_id)
        if not task:
            raise ReviewNotFoundError(str(review_id))
        if task.user_id != user_id:
            raise NotOwnerError(str(user_id))
        if task.status == ReviewStatus.COMPLETED:
            return {"id": str(task.id), "already_completed": True}
        task.status = ReviewStatus.COMPLETED
        task.completed_at = utcnow()
        task.result = {**(task.result or {}), "score": score}

        schedule = dict(task.schedule or {})
        intervals: list[int] = schedule.get("intervals") or EBBINGHAUS_DAYS
        index: int = int(schedule.get("index") or 0)
        passed = score >= 0.5
        index = min(index + 1, len(intervals) - 1) if passed else 0
        schedule["index"] = index
        task.schedule = schedule
        db.commit()

    assessment_service.apply_mastery_update(
        user_id=user_id,
        knowledge_point_id=task.knowledge_point_id,
        score=score,
        confidence=confidence,
    )
    # Chain the next spaced review (idempotent guard applies).
    schedule_review(
        user_id=user_id,
        knowledge_point_id=task.knowledge_point_id,
        review_type="SPACED",
        reason="auto after review completion",
        due_in_days=intervals[index],
    )
    memory_service.record_event(
        user_id=user_id,
        goal_id=None,
        subject_type="ReviewTask",
        subject_id=review_id,
        event_name="review.completed",
        payload={"score": score, "passed": passed, "kp": str(task.knowledge_point_id)},
    )
    return {"id": str(review_id), "passed": passed, "next_interval_days": intervals[index]}


def mark_due(user_id: uuid.UUID | None = None, *, now=None) -> int:
    """PENDING → DUE when due_at has passed. Returns how many flipped.

    Called by the daily scheduler; emits one REVIEW_DUE event per review so
    the manager loop can react (§11 event-driven automation).
    """
    now = now or utcnow()
    with SessionLocal() as db:
        stmt = select(ReviewTask).where(
            ReviewTask.status == ReviewStatus.PENDING,
            ReviewTask.due_at.is_not(None),
            ReviewTask.due_at <= now,
        )
        if user_id is not None:
            stmt = stmt.where(ReviewTask.user_id == user_id)
        due = db.scalars(stmt).all()
        for task in due:
            task.status = ReviewStatus.DUE
        db.commit()
        ids = [(str(t.id), t.user_id) for t in due]
    for review_id, owner in ids:
        bus.publish(
            EventType.REVIEW_DUE, aggregate_id=uuid.UUID(review_id), aggregate_type="ReviewTask"
        )
        memory_service.record_event(
            user_id=owner,
            goal_id=None,
            subject_type="ReviewTask",
            subject_id=uuid.UUID(review_id),
            event_name="review.due",
            payload={},
        )
    if ids:
        logger.info("review.marked_due", count=len(ids))
    return len(ids)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_reviews(
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    knowledge_point_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[dict]:
    with SessionLocal() as db:
        stmt = (
            select(ReviewTask)
            .where(ReviewTask.user_id == user_id)
            .order_by(ReviewTask.due_at.is_(None), ReviewTask.due_at)
            .limit(limit)
        )
        if status:
            stmt = stmt.where(ReviewTask.status == ReviewStatus(status))
        if knowledge_point_id:
            stmt = stmt.where(ReviewTask.knowledge_point_id == knowledge_point_id)
        return [_review_to_dict(r) for r in db.scalars(stmt).all()]


def skip_review(user_id: uuid.UUID, review_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        task = db.get(ReviewTask, review_id)
        if not task or task.user_id != user_id:
            raise ReviewNotFoundError(str(review_id))
        task.status = ReviewStatus.SKIPPED
        task.completed_at = utcnow()
        db.commit()


def _review_to_dict(r: ReviewTask) -> dict:
    return {
        "id": r.id,
        "knowledge_point_id": r.knowledge_point_id,
        "review_type": r.review_type.value if r.review_type else "SPACED",
        "status": r.status.value if r.status else None,
        "due_at": r.due_at.isoformat() if r.due_at else None,
        "interval_days": r.interval_days,
        "schedule": r.schedule or {},
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }
