"""Assessment service (whitepaper §13.2 module 8) — mastery state machine.

The whitepaper's central discipline lives here (§9): **完成不等于掌握** —
finishing tasks is not mastery. Only assessments (exercises, quizzes, 讲,
projects) update mastery. Rules, thresholds and the recency-weighted score
are deterministic business logic; the AI may propose scores, never set states.

State machine (per knowledge point):
- assessment score ≥ 0.8                → MASTERED (spaced review scheduled)
- 0.5 ≤ score < 0.8                      → REVIEW_REQUIRED (near-term review)
- score < 0.5 (with attempts)           → IN_PROGRESS
- all study tasks done, not yet assessed → COMPLETED
- fresh                                  → NOT_STARTED
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.events import EventType, bus, utcnow
from app.models.assessment import (
    Assessment,
    AssessmentType,
    MasteryRecord,
    MasteryState,
)
from app.services import memory_service

logger = structlog.get_logger("app.services.assessment")

MASTERED_THRESHOLD = 0.8
REVIEW_REQUIRED_THRESHOLD = 0.5
RECENCY_WEIGHT = 0.6  # new score weight in the blended estimate


class AssessmentServiceError(Exception):
    pass


# ---------------------------------------------------------------------------
# Recording measurements
# ---------------------------------------------------------------------------


def record_assessment(
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    knowledge_point_id: uuid.UUID,
    assessment_type: str,
    score: float,
    confidence: float,
    result: dict | None = None,
) -> dict:
    """Persist one Assessment measurement and fold it into the mastery record."""
    score = max(0.0, min(1.0, float(score)))
    confidence = max(0.0, min(1.0, float(confidence)))
    with SessionLocal() as db:
        assessment = Assessment(
            goal_id=goal_id,
            knowledge_point_id=knowledge_point_id,
            assessment_type=AssessmentType(assessment_type),
            score=score,
            confidence=confidence,
            result=result or {},
            assessed_at=utcnow(),
        )
        db.add(assessment)
        db.commit()
        assessment_id = assessment.id
    memory_service.record_event(
        user_id=user_id,
        goal_id=goal_id,
        subject_type="Assessment",
        subject_id=assessment_id,
        event_name="assessment.recorded",
        payload={
            "assessment_type": assessment_type,
            "knowledge_point_id": str(knowledge_point_id),
            "score": score,
            "confidence": confidence,
        },
    )
    return apply_mastery_update(
        user_id=user_id,
        knowledge_point_id=knowledge_point_id,
        score=score,
        confidence=confidence,
        evidence_id=assessment_id,
    )


def apply_mastery_update(
    *,
    user_id: uuid.UUID,
    knowledge_point_id: uuid.UUID,
    score: float,
    confidence: float,
    evidence_id: uuid.UUID | None = None,
) -> dict:
    """Fold a measurement into the mastery record and run the state machine.

    Score is a recency-weighted blend (60% new / 40% previous), never a
    blind overwrite. Transitions to MASTERED / REVIEW_REQUIRED automatically
    schedule the matching 温 (review) per §9.
    """
    # Lazy import: review_service imports this module for its own updates.
    from app.services import review_service

    with SessionLocal() as db:
        record = db.scalar(
            select(MasteryRecord).where(
                MasteryRecord.user_id == user_id,
                MasteryRecord.knowledge_point_id == knowledge_point_id,
            )
        )
        if record is None:
            blended, blended_conf = score, confidence
            old_state = None
        else:
            old_state = record.mastery_state
            if (
                old_state in (MasteryState.NOT_STARTED, MasteryState.COMPLETED)
                and record.score == 0.0
            ):
                blended = score  # first real measurement — no stale blend
            else:
                blended = RECENCY_WEIGHT * score + (1 - RECENCY_WEIGHT) * record.score
            blended_conf = 0.7 * confidence + 0.3 * record.confidence
        new_state = _state_for_score(blended)

        if record is None:
            record = MasteryRecord(user_id=user_id, knowledge_point_id=knowledge_point_id)
            db.add(record)
        record.score = round(blended, 4)
        record.confidence = round(blended_conf, 4)
        record.mastery_state = new_state
        record.last_assessed_at = utcnow()
        evidence = list(record.evidence or [])
        if evidence_id is not None:
            evidence.append(str(evidence_id))
        record.evidence = evidence[-50:]  # keep the trail bounded
        state_changed = old_state != new_state
        db.commit()
        result = {
            "knowledge_point_id": str(knowledge_point_id),
            "score": record.score,
            "confidence": record.confidence,
            "mastery_state": new_state.value,
            "state_changed": state_changed,
        }
    if state_changed:
        logger.info("mastery.changed", user_id=str(user_id), **result)
        bus.publish(
            EventType.MASTERY_CHANGED,
            aggregate_id=knowledge_point_id,
            aggregate_type="MasteryRecord",
            payload=result,
        )
        memory_service.record_event(
            user_id=user_id,
            goal_id=None,
            subject_type="MasteryRecord",
            subject_id=knowledge_point_id,
            event_name="mastery.changed",
            payload=result,
        )
        if new_state == MasteryState.REVIEW_REQUIRED:
            bus.publish(
                EventType.WEAKNESS_DETECTED,
                aggregate_id=knowledge_point_id,
                aggregate_type="MasteryRecord",
                payload=result,
            )
    # AUTO-REVIEW (§9 温): every assessment outcome schedules reinforcement.
    review_service.schedule_review(
        user_id=user_id,
        knowledge_point_id=knowledge_point_id,
        review_type="SPACED" if new_state == MasteryState.MASTERED else "WEAKNESS",
        reason=f"auto after assessment (state={new_state.value})",
    )
    return result


def mark_completed(user_id: uuid.UUID, knowledge_point_id: uuid.UUID) -> None:
    """STUDY tasks finished → COMPLETED, *never* downgrading an assessed state.

    This is the completion/mastery split: COMPLETED means "all teaching
    consumed", and only an assessment can move the learner further.
    """
    with SessionLocal() as db:
        record = db.scalar(
            select(MasteryRecord).where(
                MasteryRecord.user_id == user_id,
                MasteryRecord.knowledge_point_id == knowledge_point_id,
            )
        )
        if record is not None and record.mastery_state != MasteryState.NOT_STARTED:
            return  # already assessed (or completed) — never downgrade
        if record is None:
            record = MasteryRecord(user_id=user_id, knowledge_point_id=knowledge_point_id)
            db.add(record)
        record.mastery_state = MasteryState.COMPLETED
        db.commit()
    logger.info("mastery.marked_completed", user_id=str(user_id), kp=str(knowledge_point_id))


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_mastery_record(user_id: uuid.UUID, knowledge_point_id: uuid.UUID) -> dict | None:
    with SessionLocal() as db:
        record = db.scalar(
            select(MasteryRecord).where(
                MasteryRecord.user_id == user_id,
                MasteryRecord.knowledge_point_id == knowledge_point_id,
            )
        )
        return _record_to_dict(record) if record else None


def get_mastery_snapshot(user_id: uuid.UUID, knowledge_point_ids: list[uuid.UUID]) -> dict:
    """Mastery states for a set of points: {kp_id: {state, score, confidence}}."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(MasteryRecord).where(
                MasteryRecord.user_id == user_id,
                MasteryRecord.knowledge_point_id.in_(knowledge_point_ids),
            )
        ).all()
    return {str(r.knowledge_point_id): _record_to_dict(r) for r in rows}


def _state_for_score(score: float) -> MasteryState:
    if score >= MASTERED_THRESHOLD:
        return MasteryState.MASTERED
    if score >= REVIEW_REQUIRED_THRESHOLD:
        return MasteryState.REVIEW_REQUIRED
    return MasteryState.IN_PROGRESS


def _record_to_dict(r: MasteryRecord) -> dict:
    return {
        "mastery_state": r.mastery_state.value if r.mastery_state else None,
        "score": r.score,
        "confidence": r.confidence,
        "last_assessed_at": r.last_assessed_at.isoformat() if r.last_assessed_at else None,
    }
