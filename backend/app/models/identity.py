"""Identity & User module entities (whitepaper §12).

Holds account credentials and the learner profile that informs how the AI
Learning Manager tailors goals, pacing and teaching style per user.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class User(Base, UUIDPKMixin, TimestampMixin):
    """An authenticated account."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    profile: Mapped[LearnerProfile] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class LearnerProfile(Base, UUIDPKMixin, TimestampMixin):
    """Per-user learning characteristics that the AI adapts to."""

    __tablename__ = "learner_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # 学 / 练 / 用 / 讲 / 温 — dominant preferred learning method
    learning_style: Mapped[str | None] = mapped_column(String(50))
    preferred_method: Mapped[str | None] = mapped_column(String(50))
    daily_time_budget_minutes: Mapped[int | None] = mapped_column()
    weekly_target_hours: Mapped[float | None] = mapped_column()
    timezone: Mapped[str | None] = mapped_column(String(64), default="UTC")
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


class UserSession(Base, UUIDPKMixin, TimestampMixin):
    """Login session used by the auth layer (refresh / access tokens)."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), index=True)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column()
