"""Typed state schemas for the LangGraph agent graphs.

``Annotated[list, operator.add]`` fields are reducers: fan-out nodes (e.g. one
node instance per lesson) append their results without clobbering each other —
the standard LangGraph map/reduce pattern used for per-lesson generation and
quality checks.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class LearningManagerState(TypedDict, total=False):
    """State of one AI Learning Manager cycle: 观察→诊断→决策→行动→评估.

    The manager is not a 24/7 model loop (whitepaper §11): each cycle is a
    short run triggered by events (task completed, review due, ...) or the
    scheduler, and everything it observes/decides lands here.
    """

    run_id: str
    user_id: str
    goal_id: str

    # --- observe: deterministic snapshots pulled from the service layer ---
    goal: dict[str, Any]
    learner: dict[str, Any]
    tasks: list[dict[str, Any]]
    task_stats: dict[str, Any]
    path: dict[str, Any]
    mastery: dict[str, Any]
    reviews: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]

    # --- diagnose: problems identified from the 10-type taxonomy ----------
    problems: Annotated[list[dict[str, Any]], operator.add]

    # --- decide: chosen interventions, priority-ordered --------------------
    actions: list[dict[str, Any]]

    # --- act: results of executed interventions ---------------------------
    action_results: Annotated[list[dict[str, Any]], operator.add]
    messages: Annotated[list[dict[str, Any]], operator.add]  # learner-visible output

    # --- evaluate ----------------------------------------------------------
    evaluation: dict[str, Any]


class CourseAgentState(TypedDict, total=False):
    """State of one Course Agent run: generate (or revise) one course.

    The Course Agent is a temporary run (whitepaper §12): it starts from a
    goal + knowledge points, drafts an outline, writes each lesson, runs the
    content quality gate, revises failures, then hands a publishable draft to
    the curriculum service.
    """

    run_id: str
    user_id: str
    goal_id: str
    course_id: str | None

    title: str
    description: str
    knowledge_points: list[dict[str, Any]]
    learner: dict[str, Any]

    # ordered lesson plan derived from the knowledge points
    outline: list[dict[str, Any]]
    # generated lesson bodies (fan-out appends)
    lessons: Annotated[list[dict[str, Any]], operator.add]
    # final lesson set after the quality gate (single assignment from the
    # sequential gate node; bodies may be revised versions)
    final_lessons: list[dict[str, Any]]
    # content quality gate results (one per lesson)
    quality_reports: Annotated[list[dict[str, Any]], operator.add]
    path_id: str | None

    revision_count: int
    status: str  # "drafting" | "revising" | "ready" | "needs_review" | "failed"
    error: str | None
    version_id: str | None  # persisted CourseVersion id
