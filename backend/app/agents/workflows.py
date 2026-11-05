"""Agent workflows — the AI side's entry points (whitepaper §5–§10).

Each workflow wraps one agent run via ``runtime.run_agent``: services provide
the facts, the LLM proposes, services persist. Idempotency guards inside each
workflow make re-triggering safe (event storms, scheduler retries, HTTP
retries — §11): if the artifact already exists the run succeeds as a skip.

These functions are called by the automation layer (event bus / scheduler)
and by API endpoints that trigger AI work explicitly (练 exercise refresh,
讲 explanation assessment).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.agents import prompts
from app.agents.graphs import helpers
from app.agents.graphs.course_agent import build_course_agent_graph
from app.agents.graphs.learning_manager import build_learning_manager_graph
from app.agents.runtime import AgentResult, RunContext, run_agent
from app.core.database import SessionLocal
from app.core.events import EventType, bus
from app.models.agent import AgentType
from app.services import (
    assessment_service,
    curriculum_service,
    goal_service,
    knowledge_service,
    memory_service,
    practice_service,
    task_service,
    user_service,
)

log = structlog.get_logger("app.agents.workflows")

COURSE_POINTS_PER_RUN = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _learner_ctx(user_id: uuid.UUID) -> dict:
    return {
        **(user_service.get_profile(user_id) or {}),
        "memories": memory_service.list_memories(user_id),
    }


def _invoke_graph(ctx: RunContext, builder, initial: dict[str, Any]) -> dict[str, Any]:
    """Compile + invoke a graph; retries resume from the LangGraph checkpoint."""
    graph, resumable = builder(ctx)
    if resumable and ctx.attempt > 0:
        try:
            return dict(graph.invoke(None, config=ctx.graph_config))
        except Exception as exc:
            ctx.log.warning("workflow.resume_failed", error=str(exc)[:200])
    return dict(graph.invoke(initial, config=ctx.graph_config))


def _source_digest(goal_id: uuid.UUID) -> str:
    """Text of the goal's parsed reference materials (Docling/MinerU output)."""
    from app.models.content import ContentSource, SourceStatus

    with SessionLocal() as db:
        rows = db.scalars(
            select(ContentSource)
            .where(
                ContentSource.goal_id == goal_id,
                ContentSource.status == SourceStatus.PARSED,
                ContentSource.is_active.is_(True),
            )
            .limit(2)
        ).all()
    parts = []
    for row in rows:
        text = (row.parsed_content or {}).get("text") or ""
        if text:
            parts.append(f"《{row.filename or '参考材料'}》\n{text[:3000]}")
    return "\n\n".join(parts) or "（无参考材料）"


# ---------------------------------------------------------------------------
# Goal pipeline: knowledge system → path → course
# ---------------------------------------------------------------------------


def build_knowledge_system(goal_id: uuid.UUID, user_id: uuid.UUID) -> AgentResult:
    """知识体系构建 (§5.2): goal → domain + knowledge points + prerequisite edges."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        if knowledge_service.has_knowledge_system(goal_id):
            return {"skipped": "knowledge system already built"}
        goal = goal_service.get_goal(goal_id, user_id) or {}
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_BUILD_KNOWLEDGE.format(
                        goal_title=goal.get("title") or "",
                        goal_description=goal.get("description") or "（无补充描述）",
                        target_level=goal.get("target_level") or "入门到熟练",
                        success_criteria=helpers.digest(goal.get("success_criteria") or {}, 800),
                        source_digest=_source_digest(goal_id),
                        min_points=8,
                        max_points=15,
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：为目标构建知识体系。",
            schema_hint=prompts.SCHEMA_BUILD_KNOWLEDGE,
            temperature=0.4,
        )
        out.pop("_usage", None)
        points = [p for p in (out.get("knowledge_points") or []) if p.get("name")]
        if not points:
            raise ValueError("model proposed no knowledge points")
        try:
            embeddings = ctx.llm.embed(
                [f"{p.get('name', '')}\n{p.get('description', '')}" for p in points]
            )
        except Exception as exc:
            ctx.log.warning("workflow.embed_failed", error=str(exc)[:200])
            embeddings = None
        persisted = knowledge_service.persist_knowledge_system(
            goal_id,
            domain=out.get("domain") or {"name": (goal.get("title") or "目标领域")},
            knowledge_points=points,
            embeddings=embeddings,
            rationale=out.get("rationale"),
        )
        memory_service.record_event(
            user_id=user_id,
            goal_id=goal_id,
            subject_type="LearningGoal",
            subject_id=goal_id,
            event_name="knowledge_system.built",
            payload={"points": len(persisted["points"])},
        )
        bus.publish(
            EventType.KNOWLEDGE_SYSTEM_BUILT,
            aggregate_id=goal_id,
            aggregate_type="LearningGoal",
            payload={"points": len(persisted["points"])},
        )
        return {
            "domain_id": str(persisted["domain_id"]),
            "points": len(persisted["points"]),
            "skipped_points": persisted["skipped"],
        }

    return run_agent(
        fn,
        agent_type=AgentType.KNOWLEDGE_BUILDER,
        subject_type="LearningGoal",
        subject_id=str(goal_id),
        user_id=user_id,
    )


def generate_learning_path(
    goal_id: uuid.UUID, user_id: uuid.UUID, *, force: bool = False
) -> AgentResult:
    """路径规划 (§5.3): knowledge points → ordered, dependency-respecting path."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        points = knowledge_service.get_points_for_goal(goal_id)
        if not points:
            return {"skipped": "no knowledge system yet"}
        goal = goal_service.get_goal(goal_id, user_id) or {}
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_PLAN_PATH.format(
                        goal_title=goal.get("title") or "",
                        target_level=goal.get("target_level") or "入门到熟练",
                        learner_digest=helpers.digest_memories(
                            _learner_ctx(user_id).get("memories", []), 1000
                        ),
                        points_digest=helpers.digest_points(points),
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：规划学习路径。",
            schema_hint=prompts.SCHEMA_PLAN_PATH,
            temperature=0.3,
        )
        out.pop("_usage", None)
        by_code = {p["code"]: p for p in points}
        nodes = []
        for n in out.get("nodes") or []:
            point = by_code.get(n.get("knowledge_point_code"))
            if point is None:
                continue
            nodes.append(
                {
                    "order": int(n.get("order") or 0),
                    "knowledge_point_id": point["id"],
                    "sequence": n.get("sequence")
                    if n.get("sequence") in ("FIXED", "FLEXIBLE")
                    else "FIXED",
                    "est_minutes": int(n.get("est_minutes") or point.get("est_minutes") or 30),
                    "reason": n.get("reason"),
                }
            )
        # Completeness guard: the path must cover every knowledge point (§9).
        covered = {n["knowledge_point_id"] for n in nodes}
        for point in points:
            if point["id"] not in covered:
                nodes.append(
                    {
                        "order": len(nodes) + 1,
                        "knowledge_point_id": point["id"],
                        "sequence": "FLEXIBLE",
                        "est_minutes": point.get("est_minutes") or 30,
                        "reason": "补全未覆盖的知识点",
                    }
                )
        nodes.sort(key=lambda x: x["order"])
        for i, node in enumerate(nodes, start=1):
            node["order"] = i
        path = out.get("path") or {}
        path_id = curriculum_service.create_path(
            goal_id,
            title=path.get("title") or f"{goal.get('title') or '目标'} · 学习路径",
            description=path.get("description"),
            nodes=nodes,
        )
        goal_service.recompute_progress(goal_id)
        return {"path_id": str(path_id), "nodes": len(nodes), "regenerated": force}

    return run_agent(
        fn,
        agent_type=AgentType.CURRICULUM_PLANNER,
        subject_type="LearningGoal",
        subject_id=str(goal_id),
        user_id=user_id,
        payload={"force": force},
    )


def generate_course(goal_id: uuid.UUID, user_id: uuid.UUID, *, force: bool = False) -> AgentResult:
    """课程生成 (§5.4): the Course Agent graph over the path's first points."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        if not force and curriculum_service.list_courses(goal_id, published_only=True):
            return {"skipped": "a published course already exists for this goal"}
        goal = goal_service.get_goal(goal_id, user_id) or {}
        points = knowledge_service.get_points_for_goal(goal_id)
        if not points:
            return {"skipped": "no knowledge system yet"}
        path = curriculum_service.get_path_overview(goal_id) or {}
        order_by_kp = {
            str(n["knowledge_point"]["id"]): n["order"]
            for n in path.get("nodes", [])
            if n.get("knowledge_point")
        }
        points.sort(key=lambda p: order_by_kp.get(str(p["id"]), 999))
        points = points[:COURSE_POINTS_PER_RUN]
        initial = {
            "run_id": ctx.run_id,
            "user_id": str(user_id),
            "goal_id": str(goal_id),
            "title": goal.get("title") or "课程",
            "knowledge_points": points,
            "learner": _learner_ctx(user_id),
            "path_id": str(path["id"]) if path.get("id") else None,
            "status": "drafting",
        }
        return _invoke_graph(ctx, build_course_agent_graph, initial)

    return run_agent(
        fn,
        agent_type=AgentType.COURSE_AGENT,
        subject_type="LearningGoal",
        subject_id=str(goal_id),
        user_id=user_id,
        payload={"force": force},
    )


# ---------------------------------------------------------------------------
# The proactive loop (§7)
# ---------------------------------------------------------------------------


def run_manager_cycle(goal_id: uuid.UUID, user_id: uuid.UUID) -> AgentResult:
    """One 观察→诊断→决策→行动→评估 cycle for a goal."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        initial = {
            "run_id": ctx.run_id,
            "user_id": str(user_id),
            "goal_id": str(goal_id),
        }
        return _invoke_graph(ctx, build_learning_manager_graph, initial)

    return run_agent(
        fn,
        agent_type=AgentType.LEARNING_MANAGER,
        subject_type="LearningGoal",
        subject_id=str(goal_id),
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Single-capability runs (练 / 讲 / grading / memory)
# ---------------------------------------------------------------------------


def generate_exercises(
    goal_id: uuid.UUID,
    knowledge_point_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    requirement: str = "生成 3 道练习题",
    task_id: uuid.UUID | None = None,
) -> AgentResult:
    """练习生成 (§8 练)."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        point = knowledge_service.get_point_by_id(knowledge_point_id)
        if not point:
            return {"skipped": "knowledge point not found"}
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_GENERATE_EXERCISES.format(
                        point_digest=helpers.digest_points([point], 800),
                        learner_digest=helpers.digest_memories(
                            _learner_ctx(user_id).get("memories", []), 800
                        ),
                        requirement=requirement,
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：生成练习题。",
            schema_hint=prompts.SCHEMA_GENERATE_EXERCISES,
            temperature=0.5,
        )
        out.pop("_usage", None)
        questions = [q for q in (out.get("questions") or []) if q.get("question")]
        ids = practice_service.save_exercises(knowledge_point_id, questions, task_id=task_id)
        return {"exercise_ids": ids, "count": len(ids)}

    return run_agent(
        fn,
        agent_type=AgentType.EXERCISE_GENERATOR,
        subject_type="KnowledgePoint",
        subject_id=str(knowledge_point_id),
        user_id=user_id,
        payload={"goal_id": str(goal_id)},
    )


def assess_explanation(
    goal_id: uuid.UUID,
    knowledge_point_id: uuid.UUID,
    user_id: uuid.UUID,
    explanation: str,
    *,
    task_id: uuid.UUID | None = None,
) -> AgentResult:
    """讲 assessment (§8): Feynman-style explanation judged against the point."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        point = knowledge_service.get_point_by_id(knowledge_point_id)
        if not point:
            return {"skipped": "knowledge point not found"}
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_ASSESS_EXPLANATION.format(
                        point_digest=helpers.digest_points([point], 800),
                        explanation=explanation[:4000],
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：评估学习者的讲解。",
            schema_hint=prompts.SCHEMA_ASSESS_EXPLANATION,
            temperature=0.2,
        )
        out.pop("_usage", None)
        mastery = assessment_service.record_assessment(
            user_id=user_id,
            goal_id=goal_id,
            knowledge_point_id=knowledge_point_id,
            assessment_type="EXPLAIN",
            score=float(out.get("score") or 0.0),
            confidence=float(out.get("confidence") or 0.5),
            result={
                "strengths": out.get("strengths") or [],
                "gaps": out.get("gaps") or [],
                "explanation_excerpt": explanation[:200],
            },
        )
        if task_id is not None:
            task_service.complete_task(task_id, user_id)
        return {
            "mastery": mastery,
            "feedback": out.get("feedback"),
            "strengths": out.get("strengths") or [],
            "gaps": out.get("gaps") or [],
        }

    return run_agent(
        fn,
        agent_type=AgentType.ASSESSMENT_ENGINE,
        subject_type="KnowledgePoint",
        subject_id=str(knowledge_point_id),
        user_id=user_id,
        payload={"goal_id": str(goal_id), "explanation_length": len(explanation)},
    )


def grade_subjective_attempt(
    goal_id: uuid.UUID, attempt_id: uuid.UUID, user_id: uuid.UUID
) -> AgentResult:
    """AI-grade a pending subjective attempt (short answer / code)."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        attempt = practice_service.get_attempt(attempt_id)
        if not attempt:
            return {"skipped": "attempt not found"}
        if (attempt.get("feedback") or {}).get("status") != "pending_grading":
            return {"skipped": "attempt already graded"}
        exercise = practice_service.get_exercise_full(attempt["exercise_id"])
        if not exercise:
            return {"skipped": "exercise not found"}
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_GRADE_SUBJECTIVE.format(
                        question=exercise.get("prompt") or "",
                        expected_answer=exercise.get("answer") or "（无参考答案，依据知识点判断）",
                        user_answer=helpers.digest(attempt.get("user_answer") or {}, 3000),
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：为主观题评分。",
            schema_hint=prompts.SCHEMA_GRADE_SUBJECTIVE,
            temperature=0.2,
        )
        out.pop("_usage", None)
        return practice_service.record_subjective_grade(
            user_id=user_id,
            goal_id=goal_id,
            attempt_id=attempt_id,
            score=float(out.get("score") or 0.0),
            confidence=float(out.get("confidence") or 0.5),
            feedback={
                "comment": out.get("feedback"),
                "missed_points": out.get("missed_points") or [],
            },
        )

    return run_agent(
        fn,
        agent_type=AgentType.ASSESSMENT_ENGINE,
        subject_type="ExerciseAttempt",
        subject_id=str(attempt_id),
        user_id=user_id,
        payload={"goal_id": str(goal_id)},
    )


def infer_memories(user_id: uuid.UUID, goal_id: uuid.UUID | None = None) -> AgentResult:
    """记忆提取 (§12): recent events → Global Memory with source/confidence."""

    def fn(ctx: RunContext) -> dict[str, Any]:
        events = memory_service.recent_events(user_id, goal_id=goal_id, limit=60)
        if not events:
            return {"skipped": "no events to infer from"}
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_MEMORY_INFERENCE.format(
                        known_memories=helpers.digest_memories(
                            memory_service.list_memories(user_id), 1500
                        ),
                        events_digest=helpers.digest_events(events),
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：提炼学习者记忆。",
            schema_hint=prompts.SCHEMA_MEMORY_INFERENCE,
            temperature=0.2,
        )
        out.pop("_usage", None)
        accepted = 0
        for entry in out.get("memories") or []:
            if not entry.get("key") or not entry.get("source"):
                continue
            result = memory_service.upsert_memory(
                user_id=user_id,
                memory_type=entry.get("memory_type") or "BEHAVIOR",
                key=str(entry["key"])[:120],
                value=entry.get("value") or {},
                source=entry["source"],
                confidence=max(0.0, min(1.0, float(entry.get("confidence") or 0.3))),
            )
            accepted += 1 if result.get("accepted") else 0
        return {"proposed": len(out.get("memories") or []), "accepted": accepted}

    return run_agent(
        fn,
        agent_type=AgentType.MEMORY_MANAGER,
        subject_type="User",
        subject_id=str(user_id),
        user_id=user_id,
    )
