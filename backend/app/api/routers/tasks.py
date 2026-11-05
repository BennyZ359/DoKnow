"""Task & review endpoints — the daily learning surface (学/练/用/讲/温).

``GET /tasks`` returns today's plan; generation is idempotent so the client
can call ``POST /tasks/generate`` freely (it fills the daily budget with
学-then-练 tasks for the next unmastered path points).
"""

from __future__ import annotations

import uuid
from datetime import date as date_cls

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser
from app.api.schemas import ReviewCompleteRequest
from app.services import goal_service, review_service, task_service

router = APIRouter(prefix="", tags=["tasks"])


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@router.get("/tasks")
def list_tasks(
    current_user: CurrentUser,
    goal_id: uuid.UUID | None = None,
    day: str | None = Query(default=None, description="ISO 日期，默认今天"),
    status: str | None = None,
) -> dict:
    if day is None:
        from app.core.events import utcnow

        target_day = utcnow()
    else:
        try:
            target_day = date_cls.fromisoformat(day)
        except ValueError:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=f"day 不是合法日期: {day}") from None
    tasks = task_service.list_tasks(current_user, goal_id=goal_id, day=target_day, status=status)
    return {"tasks": tasks}


@router.post("/tasks/generate")
def generate_today(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    created = task_service.generate_daily_tasks(current_user, goal_id)
    return {"created": created, "tasks": task_service.list_tasks(current_user, goal_id=goal_id)}


@router.post("/tasks/{task_id}/start")
def start_task(current_user: CurrentUser, task_id: uuid.UUID) -> dict:
    return task_service.start_task(task_id, current_user)


@router.post("/tasks/{task_id}/complete")
def complete_task(current_user: CurrentUser, task_id: uuid.UUID) -> dict:
    return task_service.complete_task(task_id, current_user)


@router.post("/tasks/{task_id}/skip")
def skip_task(current_user: CurrentUser, task_id: uuid.UUID) -> dict:
    return task_service.skip_task(task_id, current_user)


@router.post("/tasks/explain")
def create_explain_task(
    current_user: CurrentUser, goal_id: uuid.UUID, knowledge_point_id: uuid.UUID
) -> dict:
    """讲 (explain) practice: explain a knowledge point in your own words."""
    goal_service.get_goal(goal_id, current_user)  # ownership check
    return task_service.create_explain_task(current_user, goal_id, knowledge_point_id)


# ---------------------------------------------------------------------------
# Reviews (温)
# ---------------------------------------------------------------------------


@router.get("/reviews")
def list_reviews(
    current_user: CurrentUser,
    status: str | None = None,
    knowledge_point_id: uuid.UUID | None = None,
) -> dict:
    return {
        "reviews": review_service.list_reviews(
            current_user, status=status, knowledge_point_id=knowledge_point_id
        )
    }


@router.post("/reviews/{review_id}/complete")
def complete_review(
    current_user: CurrentUser, review_id: uuid.UUID, body: ReviewCompleteRequest
) -> dict:
    """Complete a review; the outcome feeds the mastery state machine (§9)."""
    return review_service.complete_review(
        user_id=current_user, review_id=review_id, score=body.score
    )


@router.post("/reviews/{review_id}/skip")
def skip_review(current_user: CurrentUser, review_id: uuid.UUID) -> dict:
    review_service.skip_review(current_user, review_id)
    return {"ok": True}
