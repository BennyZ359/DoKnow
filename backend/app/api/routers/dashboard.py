"""Dashboard endpoint — the home screen aggregate.

One call gives the frontend the learner's whole world: active goal, today's
tasks, due reviews, the manager's recent messages, any pending plan proposal,
and mastery stats. This mirrors the miroFish-style home: everything the AI
has prepared for the learner today, in one glance.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.events import utcnow
from app.services import (
    assessment_service,
    curriculum_service,
    goal_service,
    intervention_service,
    knowledge_service,
    review_service,
    task_service,
    user_service,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(current_user: CurrentUser) -> dict:
    result: dict = {
        "user": user_service.get_user(current_user),
        "profile": user_service.get_profile(current_user),
        "goal": None,
        "today_tasks": [],
        "due_reviews": [],
        "manager_messages": [],
        "plan_proposal": None,
        "progress": None,
    }
    goal = goal_service.get_active_goal(current_user)
    if goal is None:
        return result

    goal_uuid = uuid.UUID(str(goal["id"]))
    points = knowledge_service.get_points_for_goal(goal_uuid)
    mastery = (
        assessment_service.get_mastery_snapshot(
            current_user, [uuid.UUID(str(p["id"])) for p in points]
        )
        if points
        else {}
    )
    mastered = sum(1 for m in mastery.values() if m.get("mastery_state") == "MASTERED")
    weak = sum(1 for m in mastery.values() if m.get("mastery_state") == "REVIEW_REQUIRED")
    path = curriculum_service.get_path_overview(goal_uuid, user_id=current_user)

    result.update(
        {
            "goal": goal,
            "today_tasks": task_service.list_tasks(
                current_user, goal_id=goal_uuid, day=utcnow(), limit=50
            ),
            "due_reviews": review_service.list_reviews(current_user, status="DUE"),
            "manager_messages": intervention_service.recent_manager_messages(
                current_user, goal_id=goal_uuid, limit=10
            ),
            "plan_proposal": intervention_service.get_pending_plan_adjustment(goal_uuid),
            "progress": {
                "goal_progress": goal.get("progress"),
                "points_total": len(points),
                "mastered": mastered,
                "review_required": weak,
                "path_nodes": len(path["nodes"]) if path else 0,
            },
        }
    )
    return result
