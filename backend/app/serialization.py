"""Explicit response mapping prevents answer keys or secrets from leaking."""

from copy import deepcopy
from datetime import datetime, timezone

from .models import Goal, KnowledgeEntry, LearningSession, Unit
from .practice import public_practice

STAGE_PROGRESS = {"learn": 0, "practice": 15, "project": 35, "teach": 55, "reflect": 75, "review": 90, "complete": 100}


def timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def session_data(item: LearningSession) -> dict:
    return {"id": item.id, "unit_id": item.unit_id, "kind": item.kind, "content": item.content,
            "feedback": item.feedback, "score": item.score, "created_at": timestamp(item.created_at),
            "assessment": item.assessment or ({"source": "unknown"} if item.score is not None else None)}


def unit_data(item: Unit, detailed: bool = False) -> dict:
    result = {"id": item.id, "goal_id": item.goal_id, "goal_title": item.goal.title,
              "title": item.title, "objective": item.objective, "position": item.position,
              "stage": item.stage, "mastery": item.mastery, "review_due_at": timestamp(item.review_due_at),
              "review_count": item.review_count, "completed_at": timestamp(item.completed_at)}
    if detailed:
        material = deepcopy(item.material)
        # Only the active question is public. Never spread the private question bank.
        result.update({name: material.get(name, {}) for name in ("lesson", "project", "teach")})
        result["practice"] = public_practice(item)
        result["sessions"] = [session_data(session) for session in item.sessions]
    return result


def goal_data(item: Goal) -> dict:
    units = [unit_data(unit) for unit in item.units]
    progress = round(sum(STAGE_PROGRESS.get(unit.stage, 0) for unit in item.units) / len(units)) if units else 0
    return {"id": item.id, "title": item.title, "motivation": item.motivation, "level": item.level,
            "daily_minutes": item.daily_minutes, "created_at": timestamp(item.created_at),
            "units": units, "progress": progress}


def knowledge_data(item: KnowledgeEntry) -> dict:
    return {"id": item.id, "title": item.title, "content": item.content,
            "source": item.source, "created_at": timestamp(item.created_at)}
