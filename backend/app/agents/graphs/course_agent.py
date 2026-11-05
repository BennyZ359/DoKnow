"""Course Agent graph (whitepaper §5.4, §8, §12) — one course per run.

A temporary agent: outline → write lessons (fan-out via Send) → content
quality gate (§10.2, one inline revision per failing lesson) → finalize
(persist draft, record quality reports, attempt publication behind the gate).

Lessons that still fail after revision get a FAILED quality report, which
blocks publication until a human resolves it (regenerate or accept) — the
AI never pushes known-bad content to a learner (§10.2 first-class gate).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from langgraph.types import Send

from app.agents import prompts
from app.agents.graphs import helpers
from app.agents.runtime import RunContext
from app.agents.state import CourseAgentState
from app.services import curriculum_service, memory_service, quality_service

log = structlog.get_logger("app.agents.course_agent")

MAX_REVISIONS_PER_LESSON = 1


def build_course_agent_graph(ctx: RunContext) -> tuple[Any, bool]:
    """Compile the course generation graph closed over one run's context."""
    from langgraph.graph import END, START, StateGraph

    # ------------------------------------------------------------ 1. 大纲
    def plan_outline(state: CourseAgentState) -> dict:
        ctx.check_deadline()
        points = state.get("knowledge_points") or []
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_COURSE_OUTLINE.format(
                        topic=state.get("title") or "",
                        points_digest=helpers.digest_points(points),
                        learner_digest=helpers.digest_memories(
                            (state.get("learner") or {}).get("memories", []), 1000
                        ),
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：生成课程大纲。",
            schema_hint=prompts.SCHEMA_COURSE_OUTLINE,
            temperature=0.4,
        )
        out.pop("_usage", None)
        by_code = {p.get("code"): p for p in points}
        outline = []
        for lesson in out.get("lessons") or []:
            codes = lesson.get("knowledge_point_codes") or []
            point = by_code.get(codes[0]) if codes else None
            outline.append(
                {
                    "order": int(lesson.get("order") or 0),
                    "title": str(lesson.get("title") or ""),
                    "objectives": lesson.get("objectives") or [],
                    "knowledge_point_code": codes[0] if codes else None,
                    "knowledge_point_id": str(point["id"]) if point else None,
                    "method": lesson.get("method") or "STUDY",
                    "est_minutes": int(lesson.get("est_minutes") or 20),
                }
            )
        outline.sort(key=lambda x: x["order"])
        for i, lesson in enumerate(outline, start=1):
            lesson["order"] = i
        ctx.log.info("course_agent.outline_ready", lessons=len(outline))
        return {
            "title": out.get("title") or state.get("title") or "课程",
            "description": out.get("description") or "",
            "outline": outline,
            "status": "drafting",
        }

    # ------------------------------------------------- 2. 写课（fan-out）
    def route_to_writers(state: CourseAgentState) -> list[Send]:
        outline = state.get("outline") or []
        used_ids = {lesson.get("knowledge_point_id") for lesson in outline}
        points_digest = helpers.digest_points(
            [p for p in state.get("knowledge_points") or [] if str(p.get("id")) in used_ids], 1500
        )
        titles = [lesson["title"] for lesson in outline]
        sends = []
        for index, lesson in enumerate(outline):
            neighbors = "；".join(
                t for i, t in enumerate(titles) if abs(i - index) == 1 and t != lesson["title"]
            )
            sends.append(
                Send(
                    "write_lesson",
                    {
                        "lesson": lesson,
                        "course_title": state.get("title") or "",
                        "points_digest": points_digest,
                        "learner_digest": helpers.digest_memories(
                            (state.get("learner") or {}).get("memories", []), 1000
                        ),
                        "neighbors": neighbors or "（无）",
                    },
                )
            )
        return sends

    def write_lesson(sent: dict) -> dict:
        ctx.check_deadline()
        lesson = sent["lesson"]
        result = ctx.llm.chat(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_WRITE_LESSON.format(
                        course_title=sent["course_title"],
                        lesson_title=lesson["title"],
                        objectives="；".join(lesson.get("objectives") or []),
                        points_digest=sent["points_digest"],
                        learner_digest=sent["learner_digest"],
                        course_memory_digest="（首次生成，暂无课程记忆）",
                        neighbors=sent["neighbors"],
                        est_minutes=lesson.get("est_minutes") or 20,
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：撰写课程内容（Markdown）。",
            temperature=0.7,
        )
        return {
            "lessons": [
                {
                    "order": lesson["order"],
                    "title": lesson["title"],
                    "body": result.content,
                    "knowledge_point_id": lesson.get("knowledge_point_id"),
                    "est_minutes": lesson.get("est_minutes") or 20,
                    "objectives": lesson.get("objectives") or [],
                }
            ]
        }

    # ------------------------------------------------ 3. 质量门禁 + 修订
    def quality_gate(state: CourseAgentState) -> dict:
        """Check each lesson; revise failing ones once; recheck.

        Sequential by design: bounded cost, deterministic bookkeeping, and
        the revision loop (§10.2) stays inspectable in one place.
        """
        ctx.check_deadline()
        lessons = sorted(state.get("lessons") or [], key=lambda x: x.get("order") or 0)
        points = {str(p.get("id")): p for p in state.get("knowledge_points") or []}
        final_lessons: list[dict] = []
        reports: list[dict] = []
        revisions = 0
        for lesson in lessons:
            ctx.check_deadline()
            point = points.get(str(lesson.get("knowledge_point_id")))
            body = lesson["body"] or ""
            report = _check_lesson(ctx, lesson, point, body)
            if not report.get("passed"):
                for _ in range(MAX_REVISIONS_PER_LESSON):
                    revisions += 1
                    body = _revise_lesson(ctx, body, report)
                    report = _check_lesson(ctx, lesson, point, body)
                    if report.get("passed"):
                        break
            lesson["body"] = body
            final_lessons.append(lesson)
            reports.append(report)
        ctx.log.info(
            "course_agent.quality_gated",
            lessons=len(final_lessons),
            passed=sum(1 for r in reports if r.get("passed")),
            revised=revisions,
        )
        return {
            "final_lessons": final_lessons,
            "quality_reports": reports,
            "revision_count": revisions,
            "status": "revising" if revisions else "drafting",
        }

    # ------------------------------------------------------------ 4. 落库
    def finalize(state: CourseAgentState) -> dict:
        ctx.check_deadline()
        goal_id = uuid.UUID(state["goal_id"])
        user_id = uuid.UUID(state["user_id"])
        lessons = state.get("final_lessons") or []
        if not lessons:
            return {"status": "failed", "error": "no lessons generated"}
        reports = {r["order"]: r for r in (state.get("quality_reports") or [])}
        try:
            draft = curriculum_service.create_course_draft(
                goal_id,
                path_id=uuid.UUID(state["path_id"]) if state.get("path_id") else None,
                title=state.get("title") or "课程",
                description=state.get("description") or "",
                lessons=[
                    {
                        "order": lesson["order"],
                        "title": lesson["title"],
                        "body": lesson["body"],
                        "summary": (lesson.get("objectives") or [""])[0],
                        "knowledge_point_id": lesson.get("knowledge_point_id"),
                        "est_minutes": lesson.get("est_minutes"),
                    }
                    for lesson in lessons
                ],
                point_ids=[
                    uuid.UUID(lesson["knowledge_point_id"])
                    for lesson in lessons
                    if lesson.get("knowledge_point_id")
                ],
            )
        except Exception as exc:
            ctx.log.error("course_agent.finalize_failed", error=str(exc)[:300])
            return {"status": "failed", "error": str(exc)[:500]}

        # Quality reports are persisted now that real lesson ids exist.
        for lesson, lesson_id in zip(lessons, draft["lesson_ids"], strict=False):
            report = reports.get(lesson["order"])
            if report is None:
                continue
            quality_service.record_report(
                subject_type="Lesson",
                subject_id=uuid.UUID(lesson_id),
                stage="GENERATION",
                status="PASSED" if report.get("passed") else "FAILED",
                score=report.get("score"),
                findings=report.get("findings") or [],
                recommendation=report.get("overall_comment"),
            )
        try:
            curriculum_service.publish_course(
                uuid.UUID(draft["course_id"]), uuid.UUID(draft["version_id"])
            )
            status = "ready"
        except curriculum_service.QualityGateError as exc:
            status = "needs_review"
            ctx.log.warning("course_agent.gate_blocked", findings=len(exc.findings))
        memory_service.record_event(
            user_id=user_id,
            goal_id=goal_id,
            subject_type="Course",
            subject_id=uuid.UUID(draft["course_id"]),
            event_name="course.generated",
            payload={"title": state.get("title"), "status": status},
        )
        return {
            "status": status,
            "course_id": draft["course_id"],
            "version_id": draft["version_id"],
            "lesson_ids": draft["lesson_ids"],
        }

    # _check_lesson / _revise_lesson defined below (closures over ctx)
    def _check_lesson(ctx_, lesson, point, body) -> dict:
        out = ctx_.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_QUALITY_CHECK.format(
                        points_digest=helpers.digest_points([point] if point else [], 800),
                        lesson_body=body,
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：严格审查课程内容质量。",
            schema_hint=prompts.SCHEMA_QUALITY_CHECK,
            temperature=0.2,
        )
        out.pop("_usage", None)
        passed = bool(out.get("passed")) and not any(
            (f.get("severity") in ("HIGH", "MEDIUM")) for f in out.get("findings") or []
        )
        return {
            "order": lesson["order"],
            "title": lesson["title"],
            "passed": passed,
            "score": out.get("score"),
            "findings": out.get("findings") or [],
            "overall_comment": out.get("overall_comment"),
        }

    def _revise_lesson(ctx_, body: str, report: dict) -> str:
        result = ctx_.llm.chat(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_REVISE_LESSON.format(
                        lesson_body=body[:8000],
                        findings=helpers.digest(report.get("findings") or [], 1200),
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：修复课程内容中的质量问题。",
            temperature=0.4,
        )
        return result.content

    builder = StateGraph(CourseAgentState)
    builder.add_node("plan_outline", plan_outline)
    builder.add_node("write_lesson", write_lesson)
    builder.add_node("quality_gate", quality_gate)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "plan_outline")
    builder.add_conditional_edges("plan_outline", route_to_writers, ["write_lesson"])
    builder.add_edge("write_lesson", "quality_gate")
    builder.add_edge("quality_gate", "finalize")
    builder.add_edge("finalize", END)

    from app.agents.graphs.learning_manager import _compile

    return _compile(ctx, builder)
