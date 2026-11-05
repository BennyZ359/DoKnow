"""Learning Goal service (whitepaper §13.2 module 2).

The goal is the entry point of the whole pipeline. Activating a goal is the
trigger that starts the autonomous chain: knowledge system → learning path →
courses (driven by the event bus, §11). This service owns goal state
transitions and progress computation; the AI only proposes.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.events import EventType, bus, utcnow
from app.models.curriculum import LearningPath, LearningPathNode
from app.models.goal import GoalStatus, LearningGoal
from app.services import memory_service

logger = structlog.get_logger("app.services.goal")


class GoalServiceError(Exception):
    pass


class GoalNotFoundError(GoalServiceError):
    pass


class InvalidTransitionError(GoalServiceError):
    pass


# Status machine (§12): DRAFT → ACTIVE ⇄ PAUSED, ACTIVE → COMPLETED → ARCHIVED
_ALLOWED: dict[GoalStatus, set[GoalStatus]] = {
    GoalStatus.DRAFT: {GoalStatus.ACTIVE, GoalStatus.ARCHIVED},
    GoalStatus.ACTIVE: {GoalStatus.PAUSED, GoalStatus.COMPLETED, GoalStatus.ARCHIVED},
    GoalStatus.PAUSED: {GoalStatus.ACTIVE, GoalStatus.ARCHIVED},
    GoalStatus.COMPLETED: {GoalStatus.ARCHIVED},
    GoalStatus.ARCHIVED: set(),
}


def _get(db, goal_id: uuid.UUID, user_id: uuid.UUID | None = None) -> LearningGoal:
    stmt = select(LearningGoal).where(LearningGoal.id == goal_id)
    if user_id is not None:
        stmt = stmt.where(LearningGoal.user_id == user_id)
    goal = db.scalar(stmt)
    if not goal:
        raise GoalNotFoundError(str(goal_id))
    return goal


def create_goal(
    user_id: uuid.UUID,
    title: str,
    *,
    description: str | None = None,
    target_level: str | None = None,
    deadline=None,
    success_criteria: dict | None = None,
    priority: int = 3,
) -> uuid.UUID:
    with SessionLocal() as db:
        goal = LearningGoal(
            user_id=user_id,
            title=title,
            description=description,
            target_level=target_level,
            deadline=deadline,
            success_criteria=success_criteria or {},
            priority=priority,
        )
        db.add(goal)
        db.commit()
        goal_id = goal.id
    memory_service.record_event(
        user_id=user_id,
        goal_id=goal_id,
        subject_type="LearningGoal",
        subject_id=goal_id,
        event_name="goal.created",
        payload={"title": title, "target_level": target_level},
    )
    logger.info("goal.created", goal_id=str(goal_id), user_id=str(user_id))
    return goal_id


def activate_goal(goal_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """DRAFT/PAUSED → ACTIVE. This is THE trigger of the autonomous pipeline."""
    with SessionLocal() as db:
        goal = _get(db, goal_id, user_id)
        if goal.status not in (GoalStatus.DRAFT, GoalStatus.PAUSED):
            raise InvalidTransitionError(f"cannot activate goal in status {goal.status}")
        goal.status = GoalStatus.ACTIVE
        if goal.started_at is None:
            goal.started_at = utcnow()
        db.commit()
    memory_service.record_event(
        user_id=user_id,
        goal_id=goal_id,
        subject_type="LearningGoal",
        subject_id=goal_id,
        event_name="goal.activated",
        payload={},
    )
    # Event-driven automation (§11): knowledge build, then path, then courses.
    bus.publish(
        EventType.LEARNING_GOAL_CREATED, aggregate_id=goal_id, aggregate_type="LearningGoal"
    )
    logger.info("goal.activated", goal_id=str(goal_id))


def update_goal(goal_id: uuid.UUID, user_id: uuid.UUID, **fields) -> None:
    allowed = {
        "title",
        "description",
        "target_level",
        "deadline",
        "success_criteria",
        "priority",
        "status",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    with SessionLocal() as db:
        goal = _get(db, goal_id, user_id)
        if "status" in clean:
            new_status = GoalStatus(clean["status"])
            if new_status not in _ALLOWED[goal.status]:
                raise InvalidTransitionError(f"{goal.status} → {new_status} not allowed")
            goal.status = new_status
        for key, value in clean.items():
            if key != "status":
                setattr(goal, key, value)
        db.commit()
    if clean:
        memory_service.record_event(
            user_id=user_id,
            goal_id=goal_id,
            subject_type="LearningGoal",
            subject_id=goal_id,
            event_name="goal.updated",
            payload=clean,
        )


def get_goal(goal_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    with SessionLocal() as db:
        goal = _get(db, goal_id, user_id)
        return _to_dict(goal)


def list_goals(user_id: uuid.UUID) -> list[dict]:
    with SessionLocal() as db:
        goals = db.scalars(
            select(LearningGoal)
            .where(LearningGoal.user_id == user_id)
            .order_by(LearningGoal.priority, LearningGoal.created_at.desc())
        ).all()
        return [_to_dict(g) for g in goals]


def get_active_goal(user_id: uuid.UUID) -> dict | None:
    with SessionLocal() as db:
        goal = db.scalar(
            select(LearningGoal)
            .where(LearningGoal.user_id == user_id, LearningGoal.status == GoalStatus.ACTIVE)
            .order_by(LearningGoal.priority, LearningGoal.created_at)
            .limit(1)
        )
        return _to_dict(goal) if goal else None


def get_goal_internal(goal_id: uuid.UUID) -> dict | None:
    """Owner-less goal read for automation wiring (internal use only)."""
    with SessionLocal() as db:
        goal = db.scalar(select(LearningGoal).where(LearningGoal.id == goal_id))
        return _to_dict(goal) if goal else None


def list_active_goals() -> list[dict]:
    """All ACTIVE goals across users — the scheduler's iteration source."""
    with SessionLocal() as db:
        goals = db.scalars(
            select(LearningGoal).where(LearningGoal.status == GoalStatus.ACTIVE)
        ).all()
        return [_to_dict(g) for g in goals]


def recompute_progress(goal_id: uuid.UUID) -> float:
    """Progress = mastered path nodes / total path nodes (§9).

    Completion of tasks does not count toward progress — only demonstrated
    mastery does (完成 ≠ 掌握). A fully mastered path completes the goal.
    """
    with SessionLocal() as db:
        goal = _get(db, goal_id)
        stmt = (
            select(LearningPathNode)
            .join(LearningPath, LearningPathNode.path_id == LearningPath.id)
            .where(LearningPath.goal_id == goal_id)
        )
        nodes = list(db.scalars(stmt).all())
        if not nodes:
            return goal.progress
        # Mastery records are joined lazily to avoid N+1 on one-shot compute.
        from app.models.assessment import MasteryRecord, MasteryState

        node_ids = [n.knowledge_point_id for n in nodes]
        mastered = set(
            db.scalars(
                select(MasteryRecord.knowledge_point_id).where(
                    MasteryRecord.knowledge_point_id.in_(node_ids),
                    MasteryRecord.user_id == goal.user_id,
                    MasteryRecord.mastery_state == MasteryState.MASTERED,
                )
            ).all()
        )
        progress = len(mastered) / len(node_ids)
        goal.progress = progress
        if progress >= 1.0 and goal.status == GoalStatus.ACTIVE:
            goal.status = GoalStatus.COMPLETED
            goal.completed_at = utcnow()
        db.commit()
        return progress


def _to_dict(goal: LearningGoal) -> dict:
    return {
        "id": goal.id,
        "user_id": goal.user_id,
        "title": goal.title,
        "description": goal.description,
        "target_level": goal.target_level,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "status": goal.status.value if goal.status else None,
        "priority": goal.priority,
        "success_criteria": goal.success_criteria or {},
        "progress": goal.progress,
        "meta": goal.meta or {},
        "started_at": goal.started_at.isoformat() if goal.started_at else None,
        "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }
