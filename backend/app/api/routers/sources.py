"""Source endpoints: upload reference materials for a goal (§5.2, §10.1).

Uploads return immediately; parsing (Docling/MinerU) happens in the
background and the client polls the source list for PARSED/FAILED status.
Parsed text is what the Knowledge Builder digests when building the goal's
knowledge system.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.api.deps import CurrentUser
from app.services import goal_service, parsing_service

router = APIRouter(prefix="/goals/{goal_id}/sources", tags=["sources"])


@router.post("")
async def upload_source(
    current_user: CurrentUser,
    goal_id: uuid.UUID,
    file: UploadFile = File(...),
    backend: str | None = Query(default=None, description="docling | mineru，缺省用全局配置"),
) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    data = await file.read()
    result = parsing_service.ingest_upload(
        goal_id=goal_id,
        user_id=current_user,
        filename=file.filename or "upload",
        data=data,
        backend=backend,
    )
    return result


@router.get("")
def list_sources(current_user: CurrentUser, goal_id: uuid.UUID) -> dict:
    goal_service.get_goal(goal_id, current_user)  # ownership check
    return {"sources": parsing_service.list_sources(goal_id)}


@router.get("/{source_id}")
def get_source(current_user: CurrentUser, goal_id: uuid.UUID, source_id: uuid.UUID) -> dict:
    """Status probe for one source (parsing progress / errors)."""
    goal_service.get_goal(goal_id, current_user)
    for source in parsing_service.list_sources(goal_id):
        if source["id"] == str(source_id):
            return source
    raise HTTPException(status_code=404, detail="参考材料不存在")
