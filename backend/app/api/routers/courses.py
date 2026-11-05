"""Course & practice endpoints — the 学 / 练 / 讲 interaction surface.

Course content is read through the publication gate: only PUBLISHED courses
are visible to learners. Exercises are generated on demand the first time a
knowledge point is practiced (AI proposes, service persists); attempts are
graded deterministically when objective, AI-graded when subjective.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.agents import workflows
from app.api.deps import CurrentUser
from app.api.schemas import AttemptRequest, ExerciseGenerateRequest, ExplanationRequest
from app.services import (
    curriculum_service,
    goal_service,
    practice_service,
    task_service,
)

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("")
def list_courses(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    return {"courses": curriculum_service.list_courses(goal_id)}


@router.get("/{course_id}")
def get_course(current_user: CurrentUser, course_id: uuid.UUID) -> dict:
    course = curriculum_service.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在或尚未发布")
    goal_service.get_goal(course["goal_id"], current_user)  # ownership check
    return course


@router.get("/{course_id}/lessons/{lesson_id}")
def get_lesson(current_user: CurrentUser, course_id: uuid.UUID, lesson_id: uuid.UUID) -> dict:
    course = curriculum_service.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在或尚未发布")
    goal_service.get_goal(course["goal_id"], current_user)
    for lesson in course["lessons"]:
        if str(lesson["id"]) == str(lesson_id):
            return lesson
    raise HTTPException(status_code=404, detail="小节不存在")


# ---------------------------------------------------------------------------
# Practice (练) — exercises live on knowledge points
# ---------------------------------------------------------------------------

practice_router = APIRouter(prefix="/knowledge-points", tags=["practice"])


@practice_router.get("/{kp_id}/exercises")
def get_exercises(current_user: CurrentUser, kp_id: uuid.UUID, goal_id: uuid.UUID) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    exercises = practice_service.get_exercises(kp_id)
    if not exercises:
        # First visit: generate a fresh set for this knowledge point (练).
        result = workflows.generate_exercises(
            goal_id, kp_id, current_user, requirement="生成 3 道练习题"
        )
        if result.status.value == "SUCCEEDED":
            exercises = practice_service.get_exercises(kp_id)
    return {"exercises": exercises}


@practice_router.post("/exercises/{exercise_id}/generate")
def regenerate_exercises(
    current_user: CurrentUser,
    exercise_id: uuid.UUID,
    goal_id: uuid.UUID,
    body: ExerciseGenerateRequest,
) -> dict:
    goal_service.get_goal(goal_id, current_user)
    exercise = practice_service.get_exercise_full(exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="练习题不存在")
    result = workflows.generate_exercises(
        goal_id,
        exercise["knowledge_point_id"],
        current_user,
        requirement=body.requirement or f"生成 {body.count} 道练习题",
    )
    return {
        "status": result.status.value,
        "exercises": practice_service.get_exercises(exercise["knowledge_point_id"]),
    }


@practice_router.post("/exercises/{exercise_id}/attempt")
def submit_attempt(
    current_user: CurrentUser, exercise_id: uuid.UUID, goal_id: uuid.UUID, body: AttemptRequest
) -> dict:
    goal_service.get_goal(goal_id, current_user)
    result = practice_service.record_attempt(
        user_id=current_user,
        goal_id=goal_id,
        exercise_id=exercise_id,
        answer=body.answer,
    )
    if result["status"] == "pending_grading":
        # Subjective question: grade asynchronously (AI assessment engine).
        from app.services import automation

        automation._spawn(
            workflows.grade_subjective_attempt,
            goal_id,
            uuid.UUID(str(result["attempt_id"])),
            current_user,
        )
    return result


# ---------------------------------------------------------------------------
# 讲 (explain) — assessed explanations
# ---------------------------------------------------------------------------

explain_router = APIRouter(prefix="/tasks", tags=["explain"])


@explain_router.post("/{task_id}/explanation")
def submit_explanation(
    current_user: CurrentUser, task_id: uuid.UUID, body: ExplanationRequest
) -> dict:
    """Submit the learner's own-words explanation for AI assessment (讲)."""

    task = task_service.list_tasks(current_user, limit=500)
    target = next((t for t in task if str(t["id"]) == str(task_id)), None)
    if not target:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not target["knowledge_point_id"]:
        raise HTTPException(status_code=422, detail="该任务未关联知识点，无法评估讲解")
    goal_service.get_goal(uuid.UUID(str(target["goal_id"])), current_user)
    result = workflows.assess_explanation(
        uuid.UUID(str(target["goal_id"])),
        uuid.UUID(str(target["knowledge_point_id"])),
        current_user,
        body.explanation,
        task_id=uuid.UUID(str(task_id)),
    )
    if result.status.value != "SUCCEEDED":
        raise HTTPException(status_code=502, detail=f"讲解评估失败：{result.error}")
    return result.output or {}


router.include_router(practice_router)
router.include_router(explain_router)
