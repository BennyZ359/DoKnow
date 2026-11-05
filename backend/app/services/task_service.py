"""Task service (whitepaper §13.2 module 5) — Learning Orchestration.

Turns the active learning path into today's concrete tasks, 学 first then 练
per knowledge point, bounded by the learner's daily time budget. Generation
is idempotent: re-running it for the same day never duplicates tasks, so the
scheduler and the manager loop can both trigger it safely (§11).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.events import EventType, bus, utcnow
from app.models.practice import LearningTask, TaskStatus, TaskType
from app.services import (
    assessment_service,
    curriculum_service,
    memory_service,
    user_service,
)

logger = structlog.get_logger("app.services.task")

STUDY = TaskType.STUDY.value
PRACTICE = TaskType.PRACTICE.value
EXPLAIN = TaskType.EXPLAIN.value

_METHOD_LABELS = {STUDY: "学", PRACTICE: "练", EXPLAIN: "讲"}


class TaskServiceError(Exception):
    pass


class TaskNotFoundError(TaskServiceError):
    pass


class NotOwnerError(TaskServiceError):
    pass


# ---------------------------------------------------------------------------
# Daily generation (idempotent)
# ---------------------------------------------------------------------------


def generate_daily_tasks(
    user_id: uuid.UUID, goal_id: uuid.UUID, *, budget_minutes: int | None = None
) -> list[dict]:
    """Create today's tasks for the goal: next unmastered path points first.

    Per point: 学 (study the published lesson) before 练 (practice); both
    before the point is considered consumed. Stops when the daily budget
    (profile or argument) is filled.
    """
    now = utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    path = curriculum_service.get_path_overview(goal_id, user_id=user_id)
    if not path or not path["nodes"]:
        return []

    if budget_minutes is None:
        profile = user_service.get_profile(user_id) or {}
        budget_minutes = int(profile.get("daily_time_budget_minutes") or 45)

    with SessionLocal() as db:
        todays = db.scalars(
            select(LearningTask).where(
                LearningTask.goal_id == goal_id,
                LearningTask.scheduled_for >= day_start,
                LearningTask.scheduled_for < day_end,
            )
        ).all()
        per_kp: dict[uuid.UUID, dict[str, LearningTask]] = {}
        for task in todays:
            if task.knowledge_point_id:
                per_kp.setdefault(task.knowledge_point_id, {})[task.task_type.value] = task

        created: list[LearningTask] = []
        filled = sum(t.est_minutes or 20 for t in todays)
        for node in path["nodes"]:
            if filled >= budget_minutes:
                break
            point = node.get("knowledge_point")
            if not point:
                continue
            mastery = node.get("mastery") or {}
            if mastery.get("mastery_state") == "MASTERED":
                continue  # already mastered — path moves on (§9)
            kp_id = point["id"]
            existing = per_kp.get(kp_id, {})
            due = now + timedelta(days=2)

            if STUDY not in existing:
                lesson = curriculum_service.get_lesson_by_kp(goal_id, kp_id)
                if lesson:
                    task = LearningTask(
                        goal_id=goal_id,
                        knowledge_point_id=kp_id,
                        task_type=TaskType.STUDY,
                        title=f"学 · {point['name']}",
                        instructions=f"学习课程《{lesson['title']}》，理解核心概念并完成课后小结。",
                        scheduled_for=now,
                        due_at=due,
                        est_minutes=lesson.get("est_minutes") or point.get("est_minutes") or 20,
                        meta={"lesson_id": str(lesson["id"])},
                    )
                    db.add(task)
                    created.append(task)
                    filled += task.est_minutes or 20
            elif PRACTICE not in existing and existing[STUDY].status == TaskStatus.COMPLETED:
                task = LearningTask(
                    goal_id=goal_id,
                    knowledge_point_id=kp_id,
                    task_type=TaskType.PRACTICE,
                    title=f"练 · {point['name']}",
                    instructions="完成本知识点的练习题，检验理解程度。",
                    scheduled_for=now,
                    due_at=due,
                    est_minutes=15,
                )
                db.add(task)
                created.append(task)
                filled += task.est_minutes
        db.commit()
        result = [_task_to_dict(t) for t in created]

    for task in result:
        memory_service.record_event(
            user_id=user_id,
            goal_id=goal_id,
            subject_type="LearningTask",
            subject_id=uuid.UUID(task["id"]),
            event_name="task.assigned",
            payload={"task_type": task["task_type"], "title": task["title"]},
        )
    if result:
        logger.info("task.daily_generated", goal_id=str(goal_id), count=len(result))
    return result


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start_task(task_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    task = _owned(task_id, user_id)
    with SessionLocal() as db:
        row = db.get(LearningTask, task.id)
        if row.status == TaskStatus.NOT_STARTED:
            row.status = TaskStatus.IN_PROGRESS
            row.started_at = utcnow()
            db.commit()
        return _task_to_dict(row)


def complete_task(task_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    task = _owned(task_id, user_id)
    with SessionLocal() as db:
        row = db.get(LearningTask, task.id)
        row.status = TaskStatus.COMPLETED
        row.completed_at = utcnow()
        db.commit()
    memory_service.record_event(
        user_id=user_id,
        goal_id=task.goal_id,
        subject_type="LearningTask",
        subject_id=task_id,
        event_name="task.completed",
        payload={"task_type": task.task_type.value},
    )
    bus.publish(
        EventType.TASK_COMPLETED,
        aggregate_id=task_id,
        aggregate_type="LearningTask",
        payload={
            "knowledge_point_id": str(task.knowledge_point_id) if task.knowledge_point_id else None
        },
    )
    # 学 finished → completion (NOT mastery!) — §9 完成≠掌握.
    if task.task_type.value == STUDY and task.knowledge_point_id:
        assessment_service.mark_completed(user_id, task.knowledge_point_id)
    return _task_to_dict(task)


def skip_task(task_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    task = _owned(task_id, user_id)
    with SessionLocal() as db:
        row = db.get(LearningTask, task.id)
        row.status = TaskStatus.SKIPPED
        row.completed_at = utcnow()
        db.commit()
        return _task_to_dict(row)


def expire_overdue_tasks() -> int:
    """PENDING-ish tasks past due → EXPIRED (scheduler sweep)."""
    now = utcnow()
    with SessionLocal() as db:
        stale = db.scalars(
            select(LearningTask).where(
                LearningTask.due_at.is_not(None),
                LearningTask.due_at < now,
                LearningTask.status.in_([TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS]),
            )
        ).all()
        for task in stale:
            task.status = TaskStatus.EXPIRED
        db.commit()
        count = len(stale)
    if count:
        logger.info("task.expired", count=count)
    return count


# ---------------------------------------------------------------------------
# On-demand task creation (interventions + API 讲)
# ---------------------------------------------------------------------------


def create_practice_task(
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    knowledge_point_id: uuid.UUID,
    *,
    title: str | None = None,
) -> dict:
    """Intervention ADD_PRACTICE: one targeted practice task, due tomorrow."""
    with SessionLocal() as db:
        task = LearningTask(
            goal_id=goal_id,
            knowledge_point_id=knowledge_point_id,
            task_type=TaskType.PRACTICE,
            title=title or "补强练习",
            instructions="AI 学习管家为你安排的针对性练习，请完成以巩固该知识点。",
            scheduled_for=utcnow(),
            due_at=utcnow() + timedelta(days=1),
            est_minutes=15,
            meta={"origin": "intervention"},
        )
        db.add(task)
        db.commit()
        task_dict = _task_to_dict(task)
    memory_service.record_event(
        user_id=user_id,
        goal_id=goal_id,
        subject_type="LearningTask",
        subject_id=task_dict["id"],
        event_name="task.assigned",
        payload={"task_type": PRACTICE, "origin": "intervention"},
    )
    return task_dict


def create_explain_task(
    user_id: uuid.UUID, goal_id: uuid.UUID, knowledge_point_id: uuid.UUID
) -> dict:
    """讲 task: the learner explains the point in their own words (§8)."""
    with SessionLocal() as db:
        task = LearningTask(
            goal_id=goal_id,
            knowledge_point_id=knowledge_point_id,
            task_type=TaskType.EXPLAIN,
            title="讲 · 用自己的话解释这个知识点",
            instructions="假设面向一位刚入门的朋友，写下你对这个知识点的完整解释（150-400字）。",
            scheduled_for=utcnow(),
            due_at=utcnow() + timedelta(days=1),
            est_minutes=10,
            meta={"origin": "learner"},
        )
        db.add(task)
        db.commit()
        return _task_to_dict(task)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_tasks(
    user_id: uuid.UUID,
    *,
    goal_id: uuid.UUID | None = None,
    day=None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Tasks for the learner; joins on goal to enforce ownership."""
    from app.models.goal import LearningGoal

    with SessionLocal() as db:
        stmt = (
            select(LearningTask)
            .join(LearningGoal, LearningTask.goal_id == LearningGoal.id)
            .where(LearningGoal.user_id == user_id)
            .order_by(LearningTask.scheduled_for.desc())
            .limit(limit)
        )
        if goal_id:
            stmt = stmt.where(LearningTask.goal_id == goal_id)
        if day is not None:
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = stmt.where(
                LearningTask.scheduled_for >= day_start,
                LearningTask.scheduled_for < day_start + timedelta(days=1),
            )
        if status:
            stmt = stmt.where(LearningTask.status == TaskStatus(status))
        return [_task_to_dict(t) for t in db.scalars(stmt).all()]


def get_path_progress_stats(user_id: uuid.UUID, goal_id: uuid.UUID) -> dict:
    """Aggregate task stats for the dashboard + manager Observe step."""
    tasks = list_tasks(user_id, goal_id=goal_id, limit=500)
    by_status: dict[str, int] = {}
    for t in tasks:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    return {
        "total": len(tasks),
        "completed": by_status.get("COMPLETED", 0),
        "in_progress": by_status.get("IN_PROGRESS", 0),
        "skipped": by_status.get("SKIPPED", 0),
        "expired": by_status.get("EXPIRED", 0),
        "not_started": by_status.get("NOT_STARTED", 0),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _owned(task_id: uuid.UUID, user_id: uuid.UUID) -> LearningTask:
    """Fetch a task enforcing user ownership (permissions live here, §13)."""
    from app.models.goal import LearningGoal

    with SessionLocal() as db:
        task = db.scalar(
            select(LearningTask)
            .join(LearningGoal, LearningTask.goal_id == LearningGoal.id)
            .where(LearningTask.id == task_id, LearningGoal.user_id == user_id)
        )
        if not task:
            raise TaskNotFoundError(f"task {task_id} not found for user")
        return task


def _task_to_dict(t: LearningTask) -> dict:
    return {
        "id": str(t.id),
        "goal_id": str(t.goal_id),
        "course_id": str(t.course_id) if t.course_id else None,
        "knowledge_point_id": str(t.knowledge_point_id) if t.knowledge_point_id else None,
        "task_type": t.task_type.value if t.task_type else None,
        "status": t.status.value if t.status else None,
        "title": t.title,
        "instructions": t.instructions,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "scheduled_for": t.scheduled_for.isoformat() if t.scheduled_for else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "est_minutes": t.est_minutes,
        "meta": t.meta or {},
    }
