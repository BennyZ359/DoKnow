"""Intervention service (whitepaper §7) — the Act step's executor.

The AI Learning Manager decides; this service executes. Each intervention is
bounded by the whitepaper's rules:

- message actions (ENCOURAGE / REMIND) are deduped per problem type within a
  day — “不要动作轰炸” (no action spam);
- ADJUST_PLAN only ever records a *proposal* on the goal; it never mutates
  the path (human-in-the-loop, §2);
- executing a plan adjustment (after the learner confirms) is a separate,
  explicit call.
"""

from __future__ import annotations

import uuid

import structlog

from app.core.database import SessionLocal
from app.core.events import EventType, bus, utcnow
from app.models.goal import LearningGoal
from app.services import memory_service, review_service, task_service

logger = structlog.get_logger("app.services.intervention")

MESSAGE_ACTIONS = {"ENCOURAGE", "REMIND"}


class InterventionServiceError(Exception):
    pass


class GoalNotFoundError(InterventionServiceError):
    pass


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute_action(
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    action: dict,
) -> dict:
    """Execute one chosen intervention. Returns {"executed", "action", ...}."""
    kind = str(action.get("action") or "NONE").upper()
    problem_type = str(action.get("problem_type") or "")
    priority = str(action.get("priority") or "LOW")
    target_id = action.get("target_id") or None
    message = str(action.get("message") or "").strip()

    result: dict = {"executed": False, "action": kind, "reason": ""}

    if kind == "NONE" or kind not in {
        "SCHEDULE_REVIEW",
        "ADD_PRACTICE",
        "SIMPLIFY_CONTENT",
        "ENCOURAGE",
        "REMIND",
        "ADJUST_PLAN",
    }:
        return result

    if kind in MESSAGE_ACTIONS:
        if not message:
            result["reason"] = "empty message"
            return result
        result.update(_send_message(user_id, goal_id, kind, problem_type, priority, message))
    elif kind == "SCHEDULE_REVIEW":
        if not target_id:
            result["reason"] = "missing target knowledge point"
            return result
        review = review_service.schedule_review(
            user_id=user_id,
            knowledge_point_id=uuid.UUID(str(target_id)),
            review_type="WEAKNESS",
            reason=f"manager intervention ({problem_type})",
        )
        result.update({"executed": True, "review_id": review["id"]})
    elif kind == "ADD_PRACTICE":
        if not target_id:
            result["reason"] = "missing target knowledge point"
            return result
        task = task_service.create_practice_task(
            user_id,
            goal_id,
            uuid.UUID(str(target_id)),
            title=f"针对性补练 · {problem_type}",
        )
        result.update({"executed": True, "task_id": task["id"]})
    elif kind == "SIMPLIFY_CONTENT":
        if not target_id:
            result["reason"] = "missing target knowledge point"
            return result
        kp_id = str(target_id)
        memory_service.upsert_memory(
            user_id=user_id,
            memory_type="KNOWLEDGE_STATE",
            key=f"simplify:{kp_id}",
            value={"knowledge_point_id": kp_id, "note": "该知识点需要降维讲解/简化内容"},
            source="AI_ASSESSMENT",
            confidence=0.7,
        )
        result.update(
            _send_message(
                user_id,
                goal_id,
                "ENCOURAGE",
                problem_type,
                priority,
                message
                or "这个知识点有点难，我注意到你在这里卡住了。可以先看简化后的讲解，再回来继续。",
            )
        )
    elif kind == "ADJUST_PLAN":
        proposal = action.get("payload") or {}
        _store_plan_proposal(goal_id, proposal, reason=action.get("reason") or problem_type)
        result.update(
            {
                "executed": True,
                "pending_confirmation": True,
                "proposal": proposal,
            }
        )

    memory_service.record_event(
        user_id=user_id,
        goal_id=goal_id,
        subject_type="Intervention",
        subject_id=None,
        event_name="intervention.executed",
        payload={"action": kind, "problem_type": problem_type, "executed": result["executed"]},
    )
    bus.publish(
        EventType.INTERVENTION_TRIGGERED,
        aggregate_id=goal_id,
        aggregate_type="LearningGoal",
        payload={"action": kind, "problem_type": problem_type},
    )
    return result


# ---------------------------------------------------------------------------
# Plan adjustment proposals (human-in-the-loop)
# ---------------------------------------------------------------------------


def _store_plan_proposal(goal_id: uuid.UUID, proposal: dict, *, reason: str) -> None:
    with SessionLocal() as db:
        goal = db.get(LearningGoal, goal_id)
        if not goal:
            raise GoalNotFoundError(str(goal_id))
        meta = dict(goal.meta or {})
        meta["pending_plan_adjustment"] = {
            "proposal": proposal,
            "reason": reason,
            "proposed_at": utcnow().isoformat(),
        }
        goal.meta = meta
        db.commit()
    logger.info("intervention.plan_proposed", goal_id=str(goal_id))


def get_pending_plan_adjustment(goal_id: uuid.UUID) -> dict | None:
    with SessionLocal() as db:
        goal = db.get(LearningGoal, goal_id)
        if not goal:
            raise GoalNotFoundError(str(goal_id))
        return (goal.meta or {}).get("pending_plan_adjustment")


def resolve_plan_adjustment(goal_id: uuid.UUID, *, accept: bool) -> dict | None:
    """Learner's decision on a proposed plan adjustment (§2 human confirmation).

    On accept, the proposal is cleared and returned to the caller, who runs
    the (idempotent) path regeneration workflow. On reject it is discarded.
    """
    with SessionLocal() as db:
        goal = db.get(LearningGoal, goal_id)
        if not goal:
            raise GoalNotFoundError(str(goal_id))
        meta = dict(goal.meta or {})
        proposal = meta.pop("pending_plan_adjustment", None)
        goal.meta = meta
        db.commit()
    logger.info("intervention.plan_resolved", goal_id=str(goal_id), accept=accept)
    return proposal if accept else None


# ---------------------------------------------------------------------------
# Learner-visible messages
# ---------------------------------------------------------------------------


def recent_manager_messages(
    user_id: uuid.UUID, *, goal_id: uuid.UUID | None = None, limit: int = 20
) -> list[dict]:
    """Manager messages the dashboard shows (newest first)."""
    events = memory_service.recent_events(user_id, goal_id=goal_id, limit=200)
    return [
        {
            "message": e["payload"].get("message", ""),
            "action": e["payload"].get("action"),
            "problem_type": e["payload"].get("problem_type"),
            "at": e["occurred_at"],
        }
        for e in reversed(events)
        if e["event_name"] == "manager.message" and e["payload"].get("message")
    ][-limit:][::-1]


def _send_message(
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    kind: str,
    problem_type: str,
    priority: str,
    message: str,
) -> dict:
    """Record a learner-visible manager message, deduped per problem per day."""
    dedupe_key = problem_type or kind
    if memory_service.has_recent_event(
        user_id,
        event_name="manager.message",
        goal_id=goal_id,
        hours=24,
        payload_key="problem_type",
        payload_value=dedupe_key,
    ):
        return {"executed": False, "reason": "deduplicated (already sent within 24h)"}
    memory_service.record_event(
        user_id=user_id,
        goal_id=goal_id,
        subject_type="Intervention",
        subject_id=None,
        event_name="manager.message",
        payload={
            "message": message,
            "action": kind,
            "problem_type": dedupe_key,
            "priority": priority,
        },
    )
    logger.info(
        "intervention.message_sent", user_id=str(user_id), action=kind, problem_type=problem_type
    )
    return {"executed": True, "message": message}
