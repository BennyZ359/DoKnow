"""Curriculum service (whitepaper §13.2 module 4).

Learning paths over knowledge points, versioned courses, and lessons. The key
invariant from the whitepaper: courses *reference* knowledge points — mastery
lives on the point, so it survives course regeneration and unlocks stay soft.

Publication is gated: a course version only becomes learner-visible when no
unresolved FAILED quality reports stand against it (§10.2).
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.events import EventType, bus, utcnow
from app.models.curriculum import (
    ContentFormat,
    Course,
    CourseStatus,
    CourseVersion,
    LearningPath,
    LearningPathNode,
    Lesson,
    PathStatus,
    Sequence,
)
from app.models.knowledge import KnowledgePoint
from app.services import quality_service

logger = structlog.get_logger("app.services.curriculum")


class CurriculumServiceError(Exception):
    pass


class GoalNotFoundError(CurriculumServiceError):
    pass


class QualityGateError(CurriculumServiceError):
    def __init__(self, findings: list[dict]):
        super().__init__("quality gate blocked publication")
        self.findings = findings


# ---------------------------------------------------------------------------
# Learning path
# ---------------------------------------------------------------------------


def create_path(
    goal_id: uuid.UUID,
    *,
    title: str,
    description: str | None,
    nodes: list[dict],
) -> uuid.UUID:
    """Persist a planned path (nodes reference knowledge point ids).

    Any previously ACTIVE path for the goal is archived: one active path.
    """
    with SessionLocal() as db:
        for old in db.scalars(
            select(LearningPath).where(
                LearningPath.goal_id == goal_id, LearningPath.status == PathStatus.ACTIVE
            )
        ).all():
            old.status = PathStatus.ARCHIVED
        path = LearningPath(
            goal_id=goal_id,
            title=title,
            description=description,
            status=PathStatus.ACTIVE,
            total_est_minutes=sum(int(n.get("est_minutes") or 30) for n in nodes),
        )
        db.add(path)
        db.flush()
        for n in sorted(nodes, key=lambda x: int(x.get("order") or 0)):
            db.add(
                LearningPathNode(
                    path_id=path.id,
                    knowledge_point_id=uuid.UUID(str(n["knowledge_point_id"])),
                    order_index=int(n.get("order") or 0),
                    sequence=Sequence(n.get("sequence") or "FIXED"),
                    est_minutes=int(n.get("est_minutes") or 30),
                    meta={"reason": n.get("reason")} if n.get("reason") else {},
                )
            )
        db.commit()
        logger.info("path.created", goal_id=str(goal_id), path_id=str(path.id), nodes=len(nodes))
        bus.publish(
            EventType.LEARNING_PATH_GENERATED,
            aggregate_id=path.id,
            aggregate_type="LearningPath",
            payload={"goal_id": str(goal_id)},
        )
        return path.id


def get_path_overview(goal_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> dict | None:
    """Active path with ordered nodes (knowledge point info attached)."""
    from app.models.assessment import MasteryRecord

    with SessionLocal() as db:
        path = db.scalar(
            select(LearningPath).where(
                LearningPath.goal_id == goal_id, LearningPath.status == PathStatus.ACTIVE
            )
        )
        if not path:
            return None
        nodes = db.scalars(
            select(LearningPathNode)
            .where(LearningPathNode.path_id == path.id)
            .order_by(LearningPathNode.order_index)
        ).all()
        point_rows = {
            p.id: p
            for p in db.scalars(
                select(KnowledgePoint).where(
                    KnowledgePoint.id.in_([n.knowledge_point_id for n in nodes])
                )
            ).all()
        }
        mastery: dict[uuid.UUID, dict] = {}
        if user_id is not None:
            for m in db.scalars(
                select(MasteryRecord).where(
                    MasteryRecord.user_id == user_id,
                    MasteryRecord.knowledge_point_id.in_([n.knowledge_point_id for n in nodes]),
                )
            ).all():
                mastery[m.knowledge_point_id] = {
                    "mastery_state": m.mastery_state.value if m.mastery_state else None,
                    "score": m.score,
                    "confidence": m.confidence,
                }
        return {
            "id": path.id,
            "goal_id": goal_id,
            "title": path.title,
            "description": path.description,
            "total_est_minutes": path.total_est_minutes,
            "nodes": [
                {
                    "order": n.order_index,
                    "sequence": n.sequence.value if n.sequence else "FIXED",
                    "est_minutes": n.est_minutes,
                    "reason": (n.meta or {}).get("reason"),
                    "knowledge_point": _point_brief(point_rows.get(n.knowledge_point_id)),
                    "mastery": mastery.get(n.knowledge_point_id),
                }
                for n in nodes
            ],
        }


# ---------------------------------------------------------------------------
# Course versions & lessons
# ---------------------------------------------------------------------------


def create_course_draft(
    goal_id: uuid.UUID,
    *,
    path_id: uuid.UUID | None,
    title: str,
    description: str | None,
    lessons: list[dict],
    point_ids: list[uuid.UUID],
    change_reason: str = "initial generation",
) -> dict:
    """Create Course + CourseVersion(v_next) + Lesson rows from a Course Agent run."""
    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.goal_id == goal_id, Course.title == title))
        if course is None:
            course = Course(goal_id=goal_id, path_id=path_id, title=title, description=description)
            db.add(course)
            db.flush()
        next_version = (
            db.scalar(
                select(CourseVersion.version_number)
                .where(CourseVersion.course_id == course.id)
                .order_by(CourseVersion.version_number.desc())
                .limit(1)
            )
            or 0
        ) + 1
        version = CourseVersion(
            course_id=course.id,
            version_number=next_version,
            change_reason=change_reason,
            knowledge_point_ids=[str(pid) for pid in point_ids],
        )
        db.add(version)
        db.flush()
        lesson_ids: list[str] = []
        kp_by_order: dict[int, uuid.UUID | None] = {}
        for i, lesson in enumerate(
            sorted(lessons, key=lambda x: int(x.get("order") or 0)), start=1
        ):
            kp_id = lesson.get("knowledge_point_id")
            row = Lesson(
                course_version_id=version.id,
                order_index=int(lesson.get("order") or i),
                title=str(lesson.get("title") or f"第 {i} 节")[:255],
                summary=lesson.get("summary") or (lesson.get("objectives") or [""])[0],
                format=ContentFormat(lesson.get("format") or "MARKDOWN"),
                body=lesson.get("body"),
                knowledge_point_id=uuid.UUID(str(kp_id)) if kp_id else None,
                est_minutes=_int_or(lesson.get("est_minutes"), 20),
            )
            db.add(row)
            lesson_ids.append(str(row.id))
            kp_by_order[row.order_index] = row.knowledge_point_id
        db.commit()
        logger.info(
            "course.draft_created",
            course_id=str(course.id),
            version=next_version,
            lessons=len(lessons),
        )
        return {
            "course_id": str(course.id),
            "version_id": str(version.id),
            "version_number": next_version,
            "lesson_ids": lesson_ids,
        }


def publish_course(course_id: uuid.UUID, version_id: uuid.UUID) -> None:
    """Quality gate (§10.2): FAILED reports block publication until resolved."""
    with SessionLocal() as db:
        course = db.get(Course, course_id)
        version = db.get(CourseVersion, version_id)
        if not course or not version:
            raise GoalNotFoundError(f"course {course_id}/version {version_id}")
        lesson_rows = db.scalars(select(Lesson).where(Lesson.course_version_id == version.id)).all()
        blocked, findings = quality_service.publication_blocked(
            version_id, [lesson.id for lesson in lesson_rows]
        )
        if blocked:
            raise QualityGateError(findings)
        version.is_published = True
        course.status = CourseStatus.PUBLISHED
        course.active_version_id = version.id
        course.total_est_minutes = sum(lesson.est_minutes or 20 for lesson in lesson_rows)
        course.published_at = utcnow()
        db.commit()
    logger.info("course.published", course_id=str(course_id), version_id=str(version_id))
    bus.publish(EventType.COURSE_GENERATED, aggregate_id=course_id, aggregate_type="Course")


def get_course(course_id: uuid.UUID, *, include_draft: bool = False) -> dict | None:
    with SessionLocal() as db:
        course = db.get(Course, course_id)
        if not course:
            return None
        if not include_draft and course.status != CourseStatus.PUBLISHED:
            return None
        version_id = course.active_version_id
        version = db.get(CourseVersion, version_id) if version_id else None
        lessons = (
            db.scalars(
                select(Lesson)
                .where(Lesson.course_version_id == version.id)
                .order_by(Lesson.order_index)
            ).all()
            if version
            else []
        )
        return {
            "id": course.id,
            "goal_id": course.goal_id,
            "title": course.title,
            "description": course.description,
            "status": course.status.value if course.status else None,
            "active_version_id": version_id,
            "total_est_minutes": course.total_est_minutes,
            "lessons": [_lesson_to_dict(lesson) for lesson in lessons],
        }


def list_courses(goal_id: uuid.UUID, *, published_only: bool = True) -> list[dict]:
    with SessionLocal() as db:
        stmt = select(Course).where(Course.goal_id == goal_id).order_by(Course.created_at)
        if published_only:
            stmt = stmt.where(Course.status == CourseStatus.PUBLISHED)
        return [
            {
                "id": c.id,
                "title": c.title,
                "description": c.description,
                "status": c.status.value if c.status else None,
                "total_est_minutes": c.total_est_minutes,
                "published_at": c.published_at.isoformat() if c.published_at else None,
            }
            for c in db.scalars(stmt).all()
        ]


def get_lesson_by_kp(goal_id: uuid.UUID, knowledge_point_id: uuid.UUID) -> dict | None:
    """Find the published lesson teaching a knowledge point (task generation)."""
    with SessionLocal() as db:
        lesson = db.scalar(
            select(Lesson)
            .join(CourseVersion, Lesson.course_version_id == CourseVersion.id)
            .join(Course, CourseVersion.course_id == Course.id)
            .where(
                Course.goal_id == goal_id,
                Course.status == CourseStatus.PUBLISHED,
                CourseVersion.is_published.is_(True),
                Lesson.knowledge_point_id == knowledge_point_id,
            )
            .order_by(Course.published_at.desc())
            .limit(1)
        )
        return _lesson_to_dict(lesson) if lesson else None


def _lesson_to_dict(lesson: Lesson) -> dict:
    return {
        "id": lesson.id,
        "order_index": lesson.order_index,
        "title": lesson.title,
        "summary": lesson.summary,
        "format": lesson.format.value if lesson.format else "MARKDOWN",
        "body": lesson.body,
        "knowledge_point_id": lesson.knowledge_point_id,
        "est_minutes": lesson.est_minutes,
    }


def _point_brief(point) -> dict | None:
    if not point:
        return None
    return {
        "id": point.id,
        "code": point.code,
        "name": point.name,
        "knowledge_type": point.knowledge_type.value if point.knowledge_type else None,
        "difficulty": point.difficulty.value if point.difficulty else None,
        "est_minutes": point.est_minutes,
    }


def _int_or(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
