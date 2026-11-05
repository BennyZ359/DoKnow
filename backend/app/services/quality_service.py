"""Content quality service (whitepaper §13.2 module 12, §10.2).

Content quality is a first-class gate, not an afterthought: every generated
lesson is checked (AI Content Checker + system rules) and every FAILED
finding must be resolved (regenerate) or accepted (human) before the
affected course version can be published.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.events import EventType, bus, utcnow
from app.models.content import (
    ContentQualityReport,
    QualityStage,
    QualityStatus,
    Reviewer,
)

logger = structlog.get_logger("app.services.quality")

CATEGORIES = ("accuracy", "completeness", "coherence", "formatting", "citation", "safety")


class QualityServiceError(Exception):
    pass


class ReportNotFoundError(QualityServiceError):
    pass


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def record_report(
    *,
    subject_type: str,  # Lesson | CourseVersion | ContentSource
    subject_id: uuid.UUID,
    status: str,  # PASSED | WARNING | FAILED
    findings: list[dict],
    score: float | None = None,
    stage: str = QualityStage.GENERATION.value,
    category: str = "overall",
    severity: str = "MEDIUM",
    recommendation: str | None = None,
) -> dict:
    """Persist one check result and emit COURSE_QUALITY_ISSUE on failure."""
    with SessionLocal() as db:
        report = ContentQualityReport(
            subject_type=subject_type,
            subject_id=subject_id,
            stage=QualityStage(stage),
            status=QualityStatus(status),
            reviewer=Reviewer.AI_CONTENT_CHECKER,
            category=category if category in CATEGORIES else "overall",
            severity=severity,
            score=score,
            findings=findings,
            recommendation=recommendation,
        )
        db.add(report)
        db.commit()
        report_id = report.id
    logger.info(
        "quality.report_recorded",
        subject_type=subject_type,
        subject_id=str(subject_id),
        status=status,
        score=score,
    )
    if status == QualityStatus.FAILED.value:
        bus.publish(
            EventType.COURSE_QUALITY_ISSUE,
            aggregate_id=subject_id,
            aggregate_type=subject_type,
            payload={"report_id": str(report_id), "findings": findings, "score": score},
        )
    return {"report_id": str(report_id), "status": status}


def resolve_report(report_id: uuid.UUID, *, resolution: str, resolved_by: str) -> None:
    """Mark a finding resolved: 'regenerated' or 'accepted' (human override)."""
    if resolution not in ("regenerated", "accepted"):
        raise QualityServiceError(f"invalid resolution: {resolution}")
    with SessionLocal() as db:
        report = db.get(ContentQualityReport, report_id)
        if not report:
            raise ReportNotFoundError(str(report_id))
        report.resolution = resolution
        report.resolved_by = resolved_by
        report.resolved_at = utcnow()
        db.commit()


def list_reports(
    *,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    stage: str | None = None,
    unresolved_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    with SessionLocal() as db:
        stmt = (
            select(ContentQualityReport)
            .order_by(ContentQualityReport.created_at.desc())
            .limit(limit)
        )
        if subject_type:
            stmt = stmt.where(ContentQualityReport.subject_type == subject_type)
        if subject_id:
            stmt = stmt.where(ContentQualityReport.subject_id == subject_id)
        if stage:
            stmt = stmt.where(ContentQualityReport.stage == QualityStage(stage))
        if unresolved_only:
            stmt = stmt.where(ContentQualityReport.resolution.is_(None))
        return [
            {
                "id": r.id,
                "subject_type": r.subject_type,
                "subject_id": r.subject_id,
                "stage": r.stage.value if r.stage else None,
                "status": r.status.value if r.status else None,
                "category": r.category,
                "severity": r.severity,
                "score": r.score,
                "findings": r.findings or [],
                "recommendation": r.recommendation,
                "resolution": r.resolution,
                "resolved_by": r.resolved_by,
            }
            for r in db.scalars(stmt).all()
        ]


# ---------------------------------------------------------------------------
# Publication gate
# ---------------------------------------------------------------------------


def publication_blocked(
    version_id: uuid.UUID, lesson_ids: list[uuid.UUID]
) -> tuple[bool, list[dict]]:
    """True when unresolved FAILED reports stand against the version/lessons."""
    subject_ids = [str(version_id)] + [str(lesson_id) for lesson_id in lesson_ids]
    unresolved = list_reports(
        subject_type="CourseVersion", subject_id=version_id, unresolved_only=True
    )
    findings = [r for r in unresolved if r["status"] == "FAILED"]
    for lesson_id in lesson_ids:
        for report in list_reports(
            subject_type="Lesson", subject_id=lesson_id, unresolved_only=True
        ):
            if report["status"] == "FAILED":
                findings.append(report)
    blocked = bool(findings)
    if blocked:
        logger.warning(
            "quality.publication_blocked",
            version_id=str(version_id),
            subjects=subject_ids,
            failures=len(findings),
        )
    return blocked, findings
