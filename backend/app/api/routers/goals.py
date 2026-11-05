"""Goal endpoints — the entry point of the whole system.

``POST /goals/{id}/activate`` is the moment the AI takes over: it publishes
LEARNING_GOAL_CREATED, and the automation chain (knowledge → path → course)
runs in the background. The client polls the goal overview to watch the
system build itself (§5 pipeline).
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException

from app.agents import workflows
from app.api.deps import CurrentUser
from app.api.schemas import GoalCreate, GoalUpdate, PlanAdjustDecision
from app.services import (
    curriculum_service,
    goal_service,
    intervention_service,
    knowledge_service,
)

router = APIRouter(prefix="/goals", tags=["goals"])


def _parse_deadline(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"deadline 不是合法日期: {value}") from None


@router.post("")
def create_goal(current_user: CurrentUser, body: GoalCreate) -> dict:
    goal_id = goal_service.create_goal(
        current_user,
        body.title,
        description=body.description,
        target_level=body.target_level,
        deadline=_parse_deadline(body.deadline),
        success_criteria=body.success_criteria,
        priority=body.priority,
    )
    return {"id": str(goal_id), "goal": goal_service.get_goal(goal_id, current_user)}


@router.get("")
def list_goals(current_user: CurrentUser) -> dict:
    return {"goals": goal_service.list_goals(current_user)}


@router.get("/{goal_id}")
def get_goal(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    return goal_service.get_goal(goal_id, current_user)


@router.patch("/{goal_id}")
def update_goal(current_user: CurrentUser, goal_id: uuid.UUID, body: GoalUpdate) -> dict:
    goal_service.update_goal(
        goal_id,
        current_user,
        title=body.title,
        description=body.description,
        target_level=body.target_level,
        deadline=body.deadline,
        success_criteria=body.success_criteria,
        priority=body.priority,
        status=body.status,
    )
    return goal_service.get_goal(goal_id, current_user)


@router.post("/{goal_id}/activate")
def activate_goal(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    goal_service.activate_goal(goal_id, current_user)
    return {"ok": True, "goal": goal_service.get_goal(goal_id, current_user)}


@router.get("/{goal_id}/overview")
def goal_overview(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    """Everything the goal screen needs: goal, knowledge, path, courses, mastery."""
    goal = goal_service.get_goal(goal_id, current_user)
    knowledge = knowledge_service.get_points_for_goal(goal_id)
    path = curriculum_service.get_path_overview(goal_id, user_id=current_user)
    courses = curriculum_service.list_courses(goal_id)
    return {
        "goal": goal,
        "knowledge_system_built": bool(knowledge),
        "knowledge_points": knowledge,
        "path": path,
        "courses": courses,
    }


@router.get("/{goal_id}/knowledge")
def goal_knowledge(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    return {"points": knowledge_service.get_points_for_goal(goal_id)}


@router.get("/{goal_id}/path")
def goal_path(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    return {"path": curriculum_service.get_path_overview(goal_id, user_id=current_user)}


@router.get("/{goal_id}/plan-adjustment")
def get_plan_adjustment(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    return {"proposal": intervention_service.get_pending_plan_adjustment(goal_id)}


@router.post("/{goal_id}/plan-adjustment/confirm")
def confirm_plan_adjustment(
    current_user: CurrentUser, goal_id: uuid.UUID, body: PlanAdjustDecision
) -> dict:
    """Human-in-the-loop (§2): the learner decides on the manager's proposal."""
    goal_service.get_goal(goal_id, current_user)  # ownership check
    proposal = intervention_service.resolve_plan_adjustment(goal_id, accept=body.accept)
    if proposal is None:
        return {"accepted": False, "replanning": False}
    # Accepted: re-plan in the background (idempotent path regeneration).
    from app.services import automation

    automation._spawn(lambda: workflows.generate_learning_path(goal_id, current_user, force=True))
    return {"accepted": True, "replanning": True, "proposal": proposal.get("proposal")}


@router.post("/{goal_id}/manager/cycle")
def trigger_manager_cycle(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    """Explicitly ask the AI 学习管家 to look at this goal now (debug/demo)."""
    goal = goal_service.get_goal(goal_id, current_user)
    if goal.get("status") != "ACTIVE":
        raise HTTPException(status_code=409, detail="只有 ACTIVE 目标可以运行管家循环")
    from app.services import automation

    automation._maybe_manager_cycle(goal_id, "manual")
    return {"ok": True, "queued": True}
