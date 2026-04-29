"""Clip metadata routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.persistence.repositories import ClipRepository

router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.get("")
def list_clips(request: Request, job_id: str | None = None) -> dict[str, list[dict[str, object]]]:
    """Read parsed clip metadata from persistence."""

    with request.app.state.agent.database.session() as connection:
        clips = ClipRepository(connection).list_for_job(job_id) if job_id else []
    return {"clips": [clip.__dict__ for clip in clips]}
