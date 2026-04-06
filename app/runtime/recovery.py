from __future__ import annotations

from app.persistence.repositories import JobsRepository
from app.runtime.state_machine import ACTIVE_STATES, JobState


class RecoveryManager:
    """Recovery shell for A1.

    Active work is not resumed yet; in-flight jobs are normalized to FAILED with
    an explicit runtime interruption reason.
    """

    def __init__(self, jobs_repository: JobsRepository) -> None:
        self.jobs_repository = jobs_repository

    def recover_interrupted_jobs(self) -> list[str]:
        recovered: list[str] = []
        for job in self.jobs_repository.list_jobs():
            state = JobState(job.state)
            if state in ACTIVE_STATES:
                self.jobs_repository.events_repository.append_event(
                    job_id=job.job_id,
                    event_type="job.recovery_started",
                    level="WARN",
                    origin="runtime.recovery",
                    message="Recovering interrupted active job",
                    payload={"previous_state": state.value},
                )
                self.jobs_repository.transition_job_state(
                    job_id=job.job_id,
                    new_state=JobState.FAILED,
                    current_step=job.current_step,
                    message="Runtime restarted while job was active; marked FAILED for explicit retry",
                    reason_code="runtime_interrupted",
                    origin="runtime.recovery",
                )
                self.jobs_repository.events_repository.append_event(
                    job_id=job.job_id,
                    event_type="job.recovery_completed",
                    level="WARN",
                    origin="runtime.recovery",
                    message="Interrupted job normalized to FAILED",
                    payload={"reason_code": "runtime_interrupted"},
                )
                recovered.append(job.job_id)
        return recovered
