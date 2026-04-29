"""Job log routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.persistence.repositories import EventRepository

router = APIRouter(prefix="/api/jobs", tags=["logs"])


@router.get("/{job_id}/logs")
def job_logs(request: Request, job_id: str) -> dict[str, list[dict[str, object]]]:
    """Return append-only job events."""

    with request.app.state.agent.database.session() as connection:
        events = EventRepository(connection).list_for_job(job_id)
    return {"events": [event.__dict__ for event in events]}
