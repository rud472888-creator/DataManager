"""Job and command skeleton routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_409_CONFLICT

from app.api.deps import require_token
from app.api.schemas import (
    CommandDecisionPayload,
    CommandRequestPayload,
    JobCreatePayload,
    JobListPayload,
    JobSummaryPayload,
)
from app.persistence.models import Job
from app.persistence.repositories import JobRepository
from app.runtime.lifecycle import JobCreateRequest, LifecycleError
from app.runtime.state_machine import CommandName

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
AuthDep = Annotated[None, Depends(require_token)]


@router.get("")
def list_jobs(request: Request) -> JobListPayload:
    """Return persisted job summaries."""

    jobs = request.app.state.agent.lifecycle.list_jobs()
    return {"jobs": [_job_summary(job) for job in jobs]}


@router.get("/{job_id}")
def get_job(request: Request, job_id: str) -> dict[str, object]:
    """Return persisted job detail."""

    with request.app.state.agent.database.session() as connection:
        job = JobRepository(connection).get(job_id)
    if job is None:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="job not found")
    return {"job": _job_summary(job)}


@router.post("")
def create_job(
    request: Request,
    payload: JobCreatePayload,
    _auth: AuthDep,
) -> dict[str, object]:
    """Transport job creation to the runtime lifecycle service."""

    try:
        job = request.app.state.agent.lifecycle.create_job(
            JobCreateRequest(
                project_name=payload["project_name"],
                source_volume_id=payload["source_volume_id"],
                dest_main_id=payload["dest_main_id"],
                dest_backup_id=payload["dest_backup_id"],
                operator_origin=payload["operator_origin"],
                policy=payload.get("policy"),
            )
        )
    except LifecycleError as exc:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "single_active_job",
                    "message": str(exc),
                    "details": {},
                }
            },
        ) from exc
    return {"job": _job_summary(job)}


@router.post("/{job_id}/command")
def request_command(
    request: Request,
    job_id: str,
    payload: CommandRequestPayload,
    _auth: AuthDep,
) -> CommandDecisionPayload:
    """Validate command shape and return conservative skeleton decisions."""

    try:
        command = CommandName(payload["command"])
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_command",
                    "message": f"Unsupported command: {payload['command']}",
                    "details": {"job_id": job_id},
                }
            },
        ) from exc
    try:
        decision = request.app.state.agent.lifecycle.request_command(job_id, command)
    except LifecycleError as exc:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "lifecycle_error",
                    "message": str(exc),
                    "details": {"job_id": job_id},
                }
            },
        ) from exc
    return {
        "job_id": job_id,
        "command": decision.command.value,
        "accepted": decision.accepted,
        "state_before": decision.state.value,
        "state_after": decision.state_after.value,
        "reason": decision.reason,
    }


def _job_summary(job: Job) -> JobSummaryPayload:
    return {
        "job_id": job.job_id,
        "project_name": job.project_name,
        "source_volume_id": job.source_volume_id,
        "dest_main_id": job.dest_main_id,
        "dest_backup_id": job.dest_backup_id,
        "state": job.state,
        "current_step": job.current_step,
    }
