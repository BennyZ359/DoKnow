"""Request schemas (pydantic) for the API layer.

Responses are plain dicts produced by the service layer — the domain models'
serialization lives with the services that own them, so the API layer stays
thin and can't drift from business semantics.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- auth ------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    learning_style: str | None = None
    preferred_method: str | None = None
    daily_time_budget_minutes: int | None = Field(default=None, ge=10, le=600)
    weekly_target_hours: float | None = Field(default=None, ge=0.5, le=80)
    timezone: str | None = None


# --- goals -----------------------------------------------------------------


class GoalCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    target_level: str | None = None
    deadline: str | None = None  # ISO date
    success_criteria: dict | None = None
    priority: int = Field(default=3, ge=1, le=5)


class GoalUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    target_level: str | None = None
    deadline: str | None = None
    success_criteria: dict | None = None
    priority: int | None = None
    status: str | None = None


class PlanAdjustDecision(BaseModel):
    accept: bool


# --- tasks / practice / review ---------------------------------------------


class TaskCompleteRequest(BaseModel):
    pass


class ExplanationRequest(BaseModel):
    """讲 (explain): the learner's own-words explanation of a knowledge point."""

    explanation: str = Field(min_length=20, max_length=8000)


class AttemptRequest(BaseModel):
    answer: dict = Field(default_factory=dict)


class ReviewCompleteRequest(BaseModel):
    score: float = Field(
        ge=0.0, le=1.0, description="本次温习的自我检验结果 0-1（可用快速测验得分）"
    )


class ExerciseGenerateRequest(BaseModel):
    requirement: str = "生成 3 道练习题"
    count: int = Field(default=3, ge=1, le=10)
