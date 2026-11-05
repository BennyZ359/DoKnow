"""Identity & User service (whitepaper §13.2 module 1).

Account lifecycle, learner profiles, and session management. Profile
preferences the user states directly are recorded as USER_INPUT memories —
the highest-trust source in the memory precedence rules (§12).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.events import utcnow
from app.models.identity import LearnerProfile, User, UserSession
from app.services import security

logger = structlog.get_logger("app.services.user")


class UserServiceError(Exception):
    pass


class EmailAlreadyRegisteredError(UserServiceError):
    pass


class AuthenticationError(UserServiceError):
    pass


class SessionNotFoundError(UserServiceError):
    pass


# ---------------------------------------------------------------------------
# Account & profile
# ---------------------------------------------------------------------------


def register_user(
    email: str, password: str, *, display_name: str | None = None
) -> tuple[uuid.UUID, str]:
    """Create an account with a default learner profile. Returns (id, token)."""
    email = email.strip().lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise EmailAlreadyRegisteredError(email)
        user = User(
            email=email, password_hash=security.hash_password(password), display_name=display_name
        )
        user.profile = LearnerProfile()
        db.add(user)
        db.commit()
        user_id = user.id
    logger.info("user.registered", user_id=str(user_id), email=email)
    token, _ = create_session(user_id)
    return user_id, token


def authenticate(email: str, password: str) -> uuid.UUID | None:
    """Verify credentials; returns user id or None (never raises on mismatch)."""
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.email == email.strip().lower(), User.is_active.is_(True))
        )
        if not user or not security.verify_password(password, user.password_hash):
            return None
        return user.id


def get_user(user_id: uuid.UUID) -> dict | None:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return None
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        }


def get_profile(user_id: uuid.UUID) -> dict | None:
    with SessionLocal() as db:
        profile = db.scalar(select(LearnerProfile).where(LearnerProfile.user_id == user_id))
        if not profile:
            return None
        return {
            "user_id": user_id,
            "learning_style": profile.learning_style,
            "preferred_method": profile.preferred_method,
            "daily_time_budget_minutes": profile.daily_time_budget_minutes,
            "weekly_target_hours": profile.weekly_target_hours,
            "timezone": profile.timezone,
        }


def update_profile(user_id: uuid.UUID, **fields) -> None:
    """Update learner profile fields (whitelisted keys only)."""
    allowed = {
        "learning_style",
        "preferred_method",
        "daily_time_budget_minutes",
        "weekly_target_hours",
        "timezone",
    }
    clean = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not clean:
        return
    with SessionLocal() as db:
        db.execute(update(LearnerProfile).where(LearnerProfile.user_id == user_id).values(**clean))
        db.commit()
    # A direct profile statement is a first-class USER_INPUT fact (§12):
    # preferences stated by the learner outrank anything the AI infers.
    from app.services import memory_service

    for key, value in clean.items():
        memory_service.upsert_memory(
            user_id=user_id,
            memory_type="LEARNING_STYLE"
            if key in ("learning_style", "preferred_method")
            else "PREFERENCE",
            key=f"profile.{key}",
            value={"value": value},
            source="USER_INPUT",
            confidence=0.95,
        )
    logger.info("user.profile_updated", user_id=str(user_id), fields=list(clean))


# ---------------------------------------------------------------------------
# Sessions (opaque tokens; hash stored, revocable)
# ---------------------------------------------------------------------------


def create_session(
    user_id: uuid.UUID, *, user_agent: str | None = None, ip_address: str | None = None
) -> tuple[str, datetime]:
    token = security.new_session_token()
    expires_at = utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    with SessionLocal() as db:
        db.add(
            UserSession(
                user_id=user_id,
                refresh_token_hash=security.hash_token(token),
                user_agent=user_agent,
                ip_address=ip_address,
                expires_at=expires_at,
            )
        )
        db.commit()
    return token, expires_at


def validate_session(token: str) -> uuid.UUID | None:
    """Resolve a token to its user id, or None if expired/revoked/unknown."""
    with SessionLocal() as db:
        session = db.scalar(
            select(UserSession).where(UserSession.refresh_token_hash == security.hash_token(token))
        )
        if not session or session.revoked_at is not None:
            return None
        if session.expires_at.replace(tzinfo=None) <= utcnow().replace(tzinfo=None):
            return None
        return session.user_id


def revoke_session(token: str) -> None:
    with SessionLocal() as db:
        result = db.execute(
            update(UserSession)
            .where(UserSession.refresh_token_hash == security.hash_token(token))
            .values(revoked_at=utcnow())
        )
        db.commit()
        if not result.rowcount:
            raise SessionNotFoundError("no such session")
