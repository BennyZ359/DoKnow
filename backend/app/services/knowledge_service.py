"""Knowledge service (whitepaper §13.2 module 3).

Persists the knowledge system the Knowledge Builder agent proposes: one
domain per goal, knowledge points (with optional embeddings for semantic
recall) and PREREQUISITE edges. The service enforces code uniqueness and
skips unknown prerequisite codes — the deterministic layer never trusts AI
output blindly.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.knowledge import (
    Difficulty,
    KnowledgeDomain,
    KnowledgePoint,
    KnowledgeRelation,
    KnowledgeType,
    RelationType,
)

logger = structlog.get_logger("app.services.knowledge")

_VALID_TYPES = {t.value for t in KnowledgeType}
_VALID_DIFFICULTIES = {d.value for d in Difficulty}
_VALID_METHODS = {"STUDY", "PRACTICE", "APPLY", "EXPLAIN", "REVIEW"}


class KnowledgeServiceError(Exception):
    pass


class GoalHasDomainError(KnowledgeServiceError):
    pass


def persist_knowledge_system(
    goal_id: uuid.UUID,
    *,
    domain: dict,
    knowledge_points: list[dict],
    embeddings: list[list[float]] | None = None,
    rationale: str | None = None,
) -> dict:
    """Create the domain, points and prerequisite edges from an agent proposal.

    Returns ``{"domain_id", "points": {code: id}, "skipped": [...]}``. Codes
    are deduped; unknown prerequisites are skipped and reported, not fatal.
    """
    with SessionLocal() as db:
        if db.scalar(select(KnowledgeDomain).where(KnowledgeDomain.goal_id == goal_id)):
            raise GoalHasDomainError(str(goal_id))

        dom = KnowledgeDomain(
            goal_id=goal_id,
            name=domain.get("name", "默认领域"),
            description=domain.get("description"),
            meta={"rationale": rationale} if rationale else {},
        )
        db.add(dom)
        db.flush()

        points: dict[str, uuid.UUID] = {}
        skipped: list[str] = []
        seen_codes: set[str] = set()
        for i, p in enumerate(knowledge_points):
            code = str(p.get("code") or f"KP-{i + 1:03d}").strip()
            if code in seen_codes:
                skipped.append(f"duplicate code {code}")
                continue
            methods = [m for m in (p.get("recommended_methods") or []) if m in _VALID_METHODS]
            ktype = (
                p.get("knowledge_type") if p.get("knowledge_type") in _VALID_TYPES else "CONCEPT"
            )
            difficulty = (
                p.get("difficulty") if p.get("difficulty") in _VALID_DIFFICULTIES else "BEGINNER"
            )
            point = KnowledgePoint(
                domain_id=dom.id,
                code=code,
                name=str(p.get("name") or code)[:200],
                description=p.get("description"),
                knowledge_type=KnowledgeType(ktype),
                difficulty=Difficulty(difficulty),
                recommended_methods=methods,
                tags=[str(t)[:64] for t in (p.get("tags") or [])][:8],
                est_minutes=_int_or(p.get("est_minutes"), 30),
                embedding=embeddings[i] if embeddings and i < len(embeddings) else None,
            )
            db.add(point)
            seen_codes.add(code)
            points[code] = point.id
        db.flush()

        for p in knowledge_points:
            code = str(p.get("code") or "").strip()
            target_id = points.get(code)
            for prereq_code in p.get("prerequisites") or []:
                source_id = points.get(str(prereq_code).strip())
                if target_id and source_id:
                    db.add(
                        KnowledgeRelation(
                            source_id=source_id,
                            target_id=target_id,
                            relation_type=RelationType.PREREQUISITE,
                            rationale=f"{prereq_code} 是 {code} 的前置",
                        )
                    )
        db.commit()
        if skipped:
            logger.warning("knowledge.persist_skipped", goal_id=str(goal_id), skipped=skipped)
        logger.info(
            "knowledge.persisted",
            goal_id=str(goal_id),
            domain_id=str(dom.id),
            points=len(points),
        )
        return {
            "domain_id": dom.id,
            "points": {k: str(v) for k, v in points.items()},
            "skipped": skipped,
        }


def has_knowledge_system(goal_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        return (
            db.scalar(select(KnowledgeDomain.id).where(KnowledgeDomain.goal_id == goal_id))
            is not None
        )


def get_points_for_goal(goal_id: uuid.UUID) -> list[dict]:
    """All knowledge points of the goal's domain (with prerequisite edges)."""
    with SessionLocal() as db:
        domain = db.scalar(select(KnowledgeDomain).where(KnowledgeDomain.goal_id == goal_id))
        if not domain:
            return []
        points = db.scalars(
            select(KnowledgePoint)
            .where(KnowledgePoint.domain_id == domain.id)
            .order_by(KnowledgePoint.created_at)
        ).all()
        relations = db.scalars(
            select(KnowledgeRelation).where(
                KnowledgeRelation.target_id.in_([p.id for p in points]),
                KnowledgeRelation.relation_type == RelationType.PREREQUISITE,
            )
        ).all()
        by_id = {p.id: p for p in points}
        prereqs: dict[str, list[str]] = {p.id: [] for p in points}
        for rel in relations:
            src = by_id.get(rel.source_id)
            if src is not None:
                prereqs[rel.target_id].append(src.code)
        return [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "knowledge_type": p.knowledge_type.value if p.knowledge_type else "CONCEPT",
                "difficulty": p.difficulty.value if p.difficulty else "BEGINNER",
                "recommended_methods": p.recommended_methods or [],
                "tags": p.tags or [],
                "est_minutes": p.est_minutes,
                "prerequisites": prereqs.get(p.id, []),
            }
            for p in points
        ]


def get_point_by_id(point_id: uuid.UUID) -> dict | None:
    with SessionLocal() as db:
        p = db.get(KnowledgePoint, point_id)
        if not p:
            return None
        return {
            "id": p.id,
            "domain_id": p.domain_id,
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "knowledge_type": p.knowledge_type.value if p.knowledge_type else None,
            "difficulty": p.difficulty.value if p.difficulty else None,
            "recommended_methods": p.recommended_methods or [],
            "tags": p.tags or [],
            "est_minutes": p.est_minutes,
        }


def get_point_by_code(goal_id: uuid.UUID, code: str) -> dict | None:
    points = get_points_for_goal(goal_id)
    for p in points:
        if p["code"] == code:
            return p
    return None


def _int_or(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
