from __future__ import annotations

from app.persistence.models import JobRecord
from app.runtime.state_machine import ACTIVE_STATES, JobState


class Scheduler:
    """Single-active-job scheduler shell for A1.

    Real scan/offload/verify execution is intentionally stubbed in this phase.
    """

    def __init__(self) -> None:
        self._active_job_id: str | None = None

    @property
    def active_job_id(self) -> str | None:
        return self._active_job_id

    def sync_from_jobs(self, jobs: list[JobRecord]) -> None:
        active = [job.job_id for job in jobs if JobState(job.state) in ACTIVE_STATES]
        self._active_job_id = active[0] if active else None

    def can_accept_active_work(self) -> bool:
        return self._active_job_id is None

    def mark_active(self, job_id: str) -> None:
        self._active_job_id = job_id

    def clear_active_if_matches(self, job_id: str) -> None:
        if self._active_job_id == job_id:
            self._active_job_id = None
