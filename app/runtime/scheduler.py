"""Single-active-job scheduler skeleton."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulerStatus:
    active_job_id: str | None
    accepts_new_job: bool
    reason: str


class SingleActiveJobScheduler:
    """Foundation scheduler enforcing v1 single-active-job policy."""

    def __init__(self) -> None:
        self._active_job_id: str | None = None

    def status(self) -> SchedulerStatus:
        if self._active_job_id is None:
            return SchedulerStatus(
                active_job_id=None,
                accepts_new_job=True,
                reason="no active job",
            )
        return SchedulerStatus(
            active_job_id=self._active_job_id,
            accepts_new_job=False,
            reason="single active offload policy",
        )

    def reserve(self, job_id: str) -> SchedulerStatus:
        status = self.status()
        if not status.accepts_new_job:
            return status
        self._active_job_id = job_id
        return self.status()
