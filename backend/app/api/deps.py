"""API dependencies: authentication and user resolution.

Sessions are opaque tokens (hash stored in ``user_sessions``) — see
app/services/security.py for the rationale. Every protected route declares
``CurrentUser`` and receives the authenticated user id; ownership checks on
specific resources live in the service layer (permissions are business rules).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.services import user_service


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> uuid.UUID:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    user_id = user_service.validate_session(authorization[len("Bearer ") :])
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user_id


CurrentUser = Annotated[uuid.UUID, Depends(get_current_user)]
