from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_runtime_agent, require_token
from app.runtime.agent import RuntimeAgent


router = APIRouter(prefix="/api/jobs", tags=["logs"])


@router.get("/{job_id}/logs", dependencies=[Depends(require_token)])
async def get_job_logs(
    job_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> dict[str, object]:
    try:
        return {
            "items": runtime_agent.list_job_logs(job_id, limit=limit, offset=offset),
            "limit": limit,
            "offset": offset,
        }
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
