from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_runtime_agent, require_token
from app.api.schemas import JobCommandRequest, JobCreateRequest
from app.runtime.agent import RuntimeAgent


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", dependencies=[Depends(require_token)], status_code=status.HTTP_201_CREATED)
async def create_job(
    request: JobCreateRequest,
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> dict[str, object]:
    try:
        return await runtime_agent.create_job(
            project_name=request.project_name,
            source_volume_id=request.source_volume_id,
            dest_main_id=request.dest_main_id,
            dest_backup_id=request.dest_backup_id,
            policy=request.policy,
            origin=request.operator_origin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", dependencies=[Depends(require_token)])
async def list_jobs(runtime_agent: RuntimeAgent = Depends(get_runtime_agent)) -> dict[str, object]:
    return {"items": runtime_agent.list_jobs()}


@router.get("/{job_id}", dependencies=[Depends(require_token)])
async def get_job(job_id: str, runtime_agent: RuntimeAgent = Depends(get_runtime_agent)) -> dict[str, object]:
    job = runtime_agent.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/{job_id}/command", dependencies=[Depends(require_token)])
async def post_job_command(
    job_id: str,
    request: JobCommandRequest,
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> dict[str, object]:
    try:
        result = await runtime_agent.handle_command(
            job_id=job_id,
            command_name=request.command,
            origin=request.operator_origin,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
    return {
        "job_id": result.job_id,
        "command": result.command,
        "accepted": result.accepted,
        "message": result.message,
        "persisted_event_id": result.persisted_event_id,
    }
