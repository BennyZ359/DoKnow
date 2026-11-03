"""Server-owned previews, atomic course changes and retained learning materials."""

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from .models import CourseChange, Goal, KnowledgeEntry, Unit, identifier, now_utc
from .serialization import timestamp


class CourseConflict(Exception):
    pass


def load_course(db: Session, goal_id: str) -> Goal:
    goal = db.scalar(select(Goal).where(Goal.id == goal_id).options(
        selectinload(Goal.units).selectinload(Unit.sessions)))
    if goal is None:
        raise HTTPException(404, "没有找到这个学习目标。")
    return goal


def active_units(goal: Goal) -> list[Unit]:
    return sorted((unit for unit in goal.units if not unit.archived), key=lambda unit: unit.position)


def snapshot(db: Session, goal: Goal) -> dict:
    linked = set(db.scalars(select(KnowledgeEntry.unit_id).where(
        KnowledgeEntry.unit_id.in_([unit.id for unit in goal.units]))))
    return {
        "title": goal.title, "level": goal.level, "daily_minutes": goal.daily_minutes,
        "goal_version": goal.version, "course_version": goal.course_version,
        "units": [{
            "id": unit.id, "title": unit.title, "objective": unit.objective,
            "position": unit.position, "version": unit.version,
            "retained": bool(unit.sessions or unit.stage != "learn" or unit.mastery or
                             unit.practice_state or unit.review_due_at or unit.review_count or
                             unit.review_streak or unit.completed_at or unit.id in linked),
        } for unit in active_units(goal)],
    }


def lock_snapshot(db: Session, goal_id: str, before: dict, *, level: str | None = None):
    """CAS and row locks; all callers are done awaiting providers before entering."""
    values = {"course_version": before["course_version"]}
    if level is not None:
        values |= {"course_version": before["course_version"] + 1, "level": level}
    result = db.execute(update(Goal).where(
        Goal.id == goal_id, Goal.version == before["goal_version"],
        Goal.course_version == before["course_version"],
    ).values(**values).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise CourseConflict
    for unit in before["units"]:
        result = db.execute(update(Unit).where(
            Unit.id == unit["id"], Unit.goal_id == goal_id, Unit.archived == 0,
            Unit.version == unit["version"],
        ).values(version=unit["version"]).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise CourseConflict


def validate_operation(before: dict, body) -> list[dict]:
    if body.course_version != before["course_version"]:
        raise CourseConflict
    targets = [unit for unit in before["units"] if not unit["retained"]]
    if not targets:
        raise HTTPException(409, "所有单元都已有学习记录，没有可调整的未开始单元。")
    if body.kind == "difficulty" and body.level == before["level"]:
        raise HTTPException(422, "请选择与当前课程不同的难度。")
    if body.kind == "reorder":
        ids = [unit["id"] for unit in targets]
        if len(ids) < 2 or len(body.unit_ids) != len(ids) or set(body.unit_ids) != set(ids):
            raise HTTPException(422, "请提供全部未开始单元，每个恰好一次；已开始单元位置固定。")
        if body.unit_ids == ids:
            raise HTTPException(422, "单元顺序尚未改变。")
    return targets


def proposal(before: dict, body, plan: list[dict] | None) -> dict:
    targets = [unit for unit in before["units"] if not unit["retained"]]
    replacements = {}
    if plan is not None:
        for old, material in zip(targets, plan, strict=True):
            replacements[old["id"]] = {
                "id": identifier(), "title": material["title"], "objective": material["objective"],
                "position": old["position"], "retained": False, "replaces": old["id"],
                "material": {key: deepcopy(material[key]) for key in (
                    "lesson", "practice", "practice_variants", "question_source", "project", "teach") if key in material},
            }
    ordered = iter(body.unit_ids or [])
    lookup = {unit["id"]: unit for unit in before["units"]}
    after = []
    for unit in before["units"]:
        if unit["retained"]:
            after.append(deepcopy(unit))
        elif body.kind == "reorder":
            after.append({**lookup[next(ordered)], "position": unit["position"]})
        else:
            after.append(replacements[unit["id"]])
    return {"level": body.level or before["level"], "units": after}


def public_unit(unit: dict) -> dict:
    value = {key: unit[key] for key in ("id", "title", "objective", "position", "retained")}
    if "replaces" in unit:
        value["replaces"] = unit["replaces"]
        # Do not expose answer keys, question banks or internal version counters.
        value.update({key: unit["material"][key] for key in ("lesson", "project", "teach")})
    return value


def change_data(change: CourseChange) -> dict:
    return {
        "id": change.id, "goal_id": change.goal_id, "kind": change.kind,
        "base_version": change.base_version, "course_version": change.base_version + 1,
        "created_at": timestamp(change.created_at), "applied_at": timestamp(change.applied_at),
        "before": {"title": change.snapshot["title"], "level": change.snapshot["level"],
                   "units": [public_unit(unit) for unit in change.snapshot["units"]]},
        "after": {"level": change.proposal["level"],
                  "units": [public_unit(unit) for unit in change.proposal["units"]]},
    }


def apply_change(db: Session, goal: Goal, change: CourseChange):
    if change.applied_at is not None or snapshot(db, goal) != change.snapshot:
        raise CourseConflict
    lock_snapshot(db, goal.id, change.snapshot, level=change.proposal["level"])
    units = {unit.id: unit for unit in active_units(goal)}
    for proposed in change.proposal["units"]:
        if proposed.get("replaces"):
            old = units[proposed["replaces"]]
            old.archived = 1
            old.updated_at = now_utc()
            goal.units.append(Unit(
                id=proposed["id"], title=proposed["title"], objective=proposed["objective"],
                position=proposed["position"], material=deepcopy(proposed["material"]),
            ))
        elif not proposed["retained"]:
            current = units[proposed["id"]]
            if current.position != proposed["position"]:
                current.position = proposed["position"]
                current.updated_at = now_utc()
    change.applied_at = now_utc()
    # Refresh Core-updated fields without dirtying Goal's independent metadata version.
    db.expire(goal, ["course_version", "level"])
