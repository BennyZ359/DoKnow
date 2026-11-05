"""Router aggregation + service-to-HTTP error mapping.

Service-layer exceptions are the API's error vocabulary: this module maps
each domain error to its HTTP status once, so endpoints never translate
errors by hand and the HTTP surface can't drift from business semantics.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from app.api.routers import auth, courses, dashboard, goals, sources, tasks
from app.services import (
    assessment_service,
    curriculum_service,
    goal_service,
    intervention_service,
    knowledge_service,
    parsing_service,
    practice_service,
    quality_service,
    review_service,
    task_service,
    user_service,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(goals.router)
api_router.include_router(courses.router)
api_router.include_router(tasks.router)
api_router.include_router(sources.router)
api_router.include_router(dashboard.router)

# (exception, status) — most specific first; Starlette walks the MRO.
_ERROR_MAP: list[tuple[type[Exception], int]] = [
    (user_service.EmailAlreadyRegisteredError, 409),
    (user_service.AuthenticationError, 401),
    (goal_service.InvalidTransitionError, 409),
    (curriculum_service.QualityGateError, 422),
    (knowledge_service.GoalHasDomainError, 409),
    (parsing_service.UnsupportedFileTypeError, 415),
    (parsing_service.FileTooLargeError, 413),
    (parsing_service.BackendUnavailableError, 503),
    (goal_service.GoalNotFoundError, 404),
    (task_service.TaskNotFoundError, 404),
    (review_service.ReviewNotFoundError, 404),
    (practice_service.ExerciseNotFoundError, 404),
    (quality_service.ReportNotFoundError, 404),
    (user_service.SessionNotFoundError, 404),
    (assessment_service.AssessmentServiceError, 400),
    (task_service.NotOwnerError, 403),
    (review_service.NotOwnerError, 403),
    (user_service.UserServiceError, 400),
    (goal_service.GoalServiceError, 400),
    (knowledge_service.KnowledgeServiceError, 400),
    (curriculum_service.CurriculumServiceError, 400),
    (task_service.TaskServiceError, 400),
    (practice_service.PracticeServiceError, 400),
    (review_service.ReviewServiceError, 400),
    (quality_service.QualityServiceError, 400),
    (intervention_service.InterventionServiceError, 400),
]


def install_exception_handlers(app: FastAPI) -> None:
    """Translate service exceptions into clean HTTP responses (once per app)."""

    def _handler(request, exc: Exception):
        status = next((code for cls, code in _ERROR_MAP if isinstance(exc, cls)), 400)
        detail = {"error": type(exc).__name__, "message": str(exc)}
        if isinstance(exc, curriculum_service.QualityGateError):
            detail["findings"] = exc.findings
        return JSONResponse(status_code=status, content=detail)

    for exc_class, _ in _ERROR_MAP:
        app.add_exception_handler(exc_class, _handler)

    # Infrastructure failures surface as clean 503s, not raw tracebacks.
    from sqlalchemy.exc import SQLAlchemyError

    def _db_handler(request, exc: Exception):
        return JSONResponse(
            status_code=503,
            content={"error": "service_unavailable", "message": "数据库暂不可用，请稍后重试"},
        )

    app.add_exception_handler(SQLAlchemyError, _db_handler)
