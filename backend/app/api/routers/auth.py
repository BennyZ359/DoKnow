"""Auth endpoints: register, login, logout, profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from app.api.deps import CurrentUser
from app.api.schemas import LoginRequest, ProfileUpdate, RegisterRequest
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterRequest) -> dict:
    user_id, token = user_service.register_user(
        body.email, body.password, display_name=body.display_name
    )
    return {"user_id": str(user_id), "token": token, "user": user_service.get_user(user_id)}


@router.post("/login")
def login(body: LoginRequest) -> dict:
    user_id = user_service.authenticate(body.email, body.password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token, expires_at = user_service.create_session(user_id)
    return {
        "user_id": str(user_id),
        "token": token,
        "expires_at": expires_at.isoformat(),
        "user": user_service.get_user(user_id),
    }


@router.post("/logout")
def logout(
    current_user: CurrentUser,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    # revoke whatever token the request carried (best effort)
    if authorization and authorization.startswith("Bearer "):
        user_service.revoke_session(authorization[len("Bearer ") :])
    return {"ok": True}


@router.get("/me")
def me(current_user: CurrentUser) -> dict:
    return {
        "user": user_service.get_user(current_user),
        "profile": user_service.get_profile(current_user),
    }


@router.patch("/me")
def update_me(current_user: CurrentUser, body: ProfileUpdate) -> dict:
    user_service.update_profile(
        current_user,
        learning_style=body.learning_style,
        preferred_method=body.preferred_method,
        daily_time_budget_minutes=body.daily_time_budget_minutes,
        weekly_target_hours=body.weekly_target_hours,
        timezone=body.timezone,
    )
    return {"ok": True, "profile": user_service.get_profile(current_user)}
