from __future__ import annotations

from pathlib import Path

from app.persistence.models import JobFileRecord
from app.persistence.repositories import JobFilesRepository
from app.persistence.repositories import JobsRepository
from app.runtime.state_machine import ACTIVE_STATES, JobState


class RecoveryManager:
    """Durable restart recovery with explicit requeue/normalize rules."""

    def __init__(
        self,
        jobs_repository: JobsRepository,
        job_files_repository: JobFilesRepository,
    ) -> None:
        self.jobs_repository = jobs_repository
        self.job_files_repository = job_files_repository

    def recover_interrupted_jobs(self) -> list[dict[str, int | str]]:
        recovered: list[dict[str, int | str]] = []
        for job in self.jobs_repository.list_jobs():
            state = JobState(job.state)
            if state in ACTIVE_STATES:
                in_progress_files = self.job_files_repository.list_in_progress(job.job_id)
                removed_partial_files = self._remove_partial_files(in_progress_files)
                self.jobs_repository.events_repository.append_event(
                    job_id=job.job_id,
                    event_type="job.recovery_started",
                    level="WARN",
                    origin="runtime.recovery",
                    message="Recovering interrupted active job",
                    payload={"previous_state": state.value},
                )
                target_state, recovery_message = self._recovery_target(state)
                affected_job_files = 0
                if target_state is JobState.FAILED:
                    affected_job_files = self.job_files_repository.mark_in_progress_as_failed(
                        job.job_id,
                        "runtime_interrupted",
                    )
                self.jobs_repository.transition_job_state(
                    job_id=job.job_id,
                    new_state=target_state,
                    current_step="queued" if target_state is JobState.QUEUED else "paused" if target_state is JobState.PAUSED else job.current_step,
                    message=recovery_message,
                    reason_code="runtime_interrupted",
                    origin="runtime.recovery",
                )
                self.jobs_repository.events_repository.append_event(
                    job_id=job.job_id,
                    event_type="job.recovery_completed",
                    level="WARN",
                    origin="runtime.recovery",
                    message=recovery_message,
                    payload={
                        "reason_code": "runtime_interrupted",
                        "recovered_state": target_state.value,
                        "affected_job_files": affected_job_files,
                        "removed_partial_files": removed_partial_files,
                    },
                )
                recovered.append(
                    {
                        "job_id": job.job_id,
                        "recovered_state": target_state.value,
                        "affected_job_files": affected_job_files,
                        "removed_partial_files": removed_partial_files,
                    }
                )
        return recovered

    @staticmethod
    def _recovery_target(state: JobState) -> tuple[JobState, str]:
        if state in {JobState.SCANNING, JobState.PREPARING}:
            return JobState.QUEUED, "Runtime restarted before data transfer; job requeued safely"
        if state is JobState.PAUSING:
            return JobState.PAUSED, "Runtime restarted during pause transition; job preserved as PAUSED"
        return JobState.FAILED, "Runtime restarted while job was active; marked FAILED for explicit retry"

    @staticmethod
    def _remove_partial_files(job_files: list[JobFileRecord]) -> int:
        removed = 0
        for record in job_files:
            metadata = record.metadata()
            for key in ("main_temp_path", "backup_temp_path"):
                raw_path = metadata.get(key)
                if not raw_path:
                    continue
                path = Path(raw_path)
                if path.exists():
                    path.unlink()
                    removed += 1
        return removed
