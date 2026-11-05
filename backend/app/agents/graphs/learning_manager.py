"""AI Learning Manager graph — the proactive intervention loop (§6–§7).

One LangGraph run = one cycle of 观察 → 诊断 → 决策 → 行动 → 评估.

Not a 24/7 model: cycles are short runs triggered by events (task completed,
review due) or the scheduler. Every node reads through services and every
mutation is executed by the deterministic intervention service — the manager
never touches the database itself (§13 AI/业务边界).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.agents import prompts
from app.agents.graphs import helpers
from app.agents.runtime import RunContext
from app.agents.state import LearningManagerState
from app.services import (
    assessment_service,
    curriculum_service,
    goal_service,
    intervention_service,
    memory_service,
    review_service,
    task_service,
    user_service,
)

log = structlog.get_logger("app.agents.learning_manager")

MAX_ACTIONS = 3


def build_learning_manager_graph(ctx: RunContext) -> tuple[Any, bool]:
    """Compile the manager cycle graph closed over one run's context.

    Returns ``(compiled_graph, resumable)`` — resumable means a Postgres
    checkpointer is attached, so a retried run continues from its checkpoint.
    """
    from langgraph.graph import END, START, StateGraph

    # ------------------------------------------------------------ 1. 观察
    def observe(state: LearningManagerState) -> dict:
        ctx.check_deadline()
        user_id = uuid.UUID(state["user_id"])
        goal_id = uuid.UUID(state["goal_id"])
        path = curriculum_service.get_path_overview(goal_id, user_id=user_id) or {"nodes": []}
        kp_ids = [
            uuid.UUID(n["knowledge_point"]["id"]) for n in path["nodes"] if n.get("knowledge_point")
        ]
        return {
            "goal": goal_service.get_goal(goal_id, user_id) or {},
            "learner": {
                **(user_service.get_profile(user_id) or {}),
                "memories": memory_service.list_memories(user_id),
            },
            "path": {"total": len(path["nodes"]), "nodes": path["nodes"]},
            "tasks": task_service.list_tasks(user_id, goal_id=goal_id, limit=60),
            "task_stats": task_service.get_path_progress_stats(user_id, goal_id),
            "mastery": assessment_service.get_mastery_snapshot(user_id, kp_ids),
            "reviews": review_service.list_reviews(user_id, status="DUE"),
            "recent_events": memory_service.recent_events(user_id, goal_id=goal_id, limit=40),
        }

    # ------------------------------------------------------------ 2. 诊断
    def diagnose(state: LearningManagerState) -> dict:
        ctx.check_deadline()
        if not state.get("tasks") and not state.get("recent_events"):
            return {"problems": []}  # brand-new goal: nothing to reason over yet
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_DIAGNOSE.format(
                        goal_digest=helpers.digest(state.get("goal", {}), 1200),
                        learner_digest=helpers.digest_memories(
                            (state.get("learner") or {}).get("memories", []), 1200
                        ),
                        tasks_digest=helpers.digest_tasks(state.get("tasks") or []),
                        mastery_digest=helpers.digest_mastery(state.get("mastery") or {}),
                        events_digest=helpers.digest_events(state.get("recent_events") or []),
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：基于真实数据诊断学习者的问题。",
            schema_hint=prompts.SCHEMA_DIAGNOSE,
            temperature=0.2,
        )
        out.pop("_usage", None)
        problems = [p for p in (out.get("problems") or []) if p.get("type")][:10]
        ctx.log.info("manager.diagnosed", problems=[p.get("type") for p in problems])
        return {"problems": problems}

    # ------------------------------------------------------------ 3. 决策
    def decide(state: LearningManagerState) -> dict:
        ctx.check_deadline()
        problems = state.get("problems") or []
        if not problems:
            return {"actions": []}  # 状态正常：不为了干预而干预
        recent = [
            e
            for e in (state.get("recent_events") or [])
            if e.get("event_name") in ("intervention.executed", "manager.message")
        ][-5:]
        out = ctx.llm.chat_json(
            [
                {
                    "role": "user",
                    "content": prompts.PROMPT_DECIDE.format(
                        problems_digest=helpers.digest(problems, 2500),
                        goal_digest=helpers.digest(state.get("goal", {}), 1200),
                        max_actions=MAX_ACTIONS,
                        recent_interventions=helpers.digest_events(recent, 800) or "（无）",
                    ),
                }
            ],
            system=prompts.PRINCIPLES + "\n\n你当前的任务是：决定本轮要采取的干预措施。",
            schema_hint=prompts.SCHEMA_DECIDE,
            temperature=0.3,
        )
        out.pop("_usage", None)
        actions = [
            a
            for a in (out.get("actions") or [])
            if str(a.get("action") or "NONE").upper() not in ("NONE", "")
        ][:MAX_ACTIONS]
        ctx.log.info("manager.decided", actions=[a.get("action") for a in actions])
        return {"actions": actions}

    # ------------------------------------------------------------ 4. 行动
    def act(state: LearningManagerState) -> dict:
        ctx.check_deadline()
        user_id = uuid.UUID(state["user_id"])
        goal_id = uuid.UUID(state["goal_id"])
        results: list[dict] = []
        messages: list[dict] = []
        for action in state.get("actions") or []:
            try:
                result = intervention_service.execute_action(
                    user_id=user_id, goal_id=goal_id, action=action
                )
                results.append({"action": action.get("action"), **result})
                if result.get("executed") and action.get("message"):
                    messages.append(
                        {
                            "message": action["message"],
                            "action": action.get("action"),
                            "problem_type": action.get("problem_type"),
                        }
                    )
            except Exception as exc:
                ctx.log.warning(
                    "manager.action_failed", action=action.get("action"), error=str(exc)[:200]
                )
                results.append(
                    {"action": action.get("action"), "executed": False, "error": str(exc)[:200]}
                )
        return {"action_results": results, "messages": messages}

    # ------------------------------------------------------------ 5. 评估
    def evaluate(state: LearningManagerState) -> dict:
        ctx.check_deadline()
        goal_id = uuid.UUID(state["goal_id"])
        user_id = uuid.UUID(state["user_id"])
        problems = state.get("problems") or []
        action_results = state.get("action_results") or []
        if problems:
            out = ctx.llm.chat_json(
                [
                    {
                        "role": "user",
                        "content": prompts.PROMPT_EVALUATE_CYCLE.format(
                            problems_digest=helpers.digest(problems, 1200),
                            results_digest=helpers.digest(action_results, 1500),
                        ),
                    }
                ],
                system=prompts.PRINCIPLES + "\n\n你当前的任务是：评估本轮干预并给出小结。",
                schema_hint=prompts.SCHEMA_EVALUATE_CYCLE,
                temperature=0.3,
            )
            out.pop("_usage", None)
        else:
            out = {
                "summary": "状态正常，本轮无需干预。",
                "interventions_had_effect": False,
                "watch_types": [],
            }
        memory_service.record_event(
            user_id=user_id,
            goal_id=goal_id,
            subject_type="LearningGoal",
            subject_id=goal_id,
            event_name="manager.cycle",
            payload={
                "summary": out.get("summary"),
                "problems": [p.get("type") for p in problems],
                "actions": [
                    {"action": a.get("action"), "executed": a.get("executed")}
                    for a in action_results
                ],
            },
        )
        goal_service.recompute_progress(goal_id)
        return {"evaluation": out}

    builder = StateGraph(LearningManagerState)
    builder.add_node("observe", observe)
    builder.add_node("diagnose", diagnose)
    builder.add_node("decide", decide)
    builder.add_node("act", act)
    builder.add_node("evaluate", evaluate)
    builder.add_edge(START, "observe")
    builder.add_edge("observe", "diagnose")
    builder.add_edge("diagnose", "decide")
    builder.add_edge("decide", "act")
    builder.add_edge("act", "evaluate")
    builder.add_edge("evaluate", END)
    return _compile(ctx, builder)


def _compile(ctx: RunContext, builder) -> tuple[Any, bool]:
    """Attach the Postgres checkpointer when the DB is reachable."""
    from app.agents.runtime import get_checkpointer

    try:
        checkpointer = get_checkpointer()
    except Exception as exc:
        ctx.log.debug("manager.no_checkpointer", error=str(exc)[:200])
        return builder.compile(), False
    return builder.compile(checkpointer=checkpointer), True
