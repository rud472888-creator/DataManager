from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import get_runtime_agent, require_token
from app.runtime.agent import RuntimeAgent
from app.runtime.reports import resolve_report_content


router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/jobs/{job_id}/reports", dependencies=[Depends(require_token)])
async def get_job_reports(
    job_id: str,
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> dict[str, object]:
    if runtime_agent.get_job(job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {"items": runtime_agent.list_reports(job_id)}


@router.get("/reports/{report_id}/content", dependencies=[Depends(require_token)])
async def get_report_content(
    report_id: str,
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> FileResponse:
    try:
        _, path, media_type = resolve_report_content(
            report_id=report_id,
            settings=runtime_agent.settings,
            persistence=runtime_agent.persistence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report index is stale",
        ) from exc
    return FileResponse(path, filename=path.name, media_type=media_type)
