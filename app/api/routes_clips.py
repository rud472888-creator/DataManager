from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_runtime_agent, require_token
from app.runtime.agent import RuntimeAgent


router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.get("", dependencies=[Depends(require_token)])
async def list_clips(
    job_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> dict[str, object]:
    return {
        "items": runtime_agent.list_clips(job_id=job_id, limit=limit, offset=offset),
        "limit": limit,
        "offset": offset,
    }
