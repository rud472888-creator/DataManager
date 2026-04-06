from __future__ import annotations

from pathlib import Path

from app.persistence.models import JobFileRecord
from app.persistence.repositories import JobFilesRepository
from app.persistence.repositories import JobsRepository
from app.runtime.state_machine import ACTIVE_STATES, JobState


class RecoveryManager:
    """Recovery shell for A1.

    Active work is not resumed yet; in-flight jobs are normalized to FAILED with
    an explicit runtime interruption reason.
    """

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
                self.jobs_repository.transition_job_state(
                    job_id=job.job_id,
                    new_state=JobState.FAILED,
                    current_step=job.current_step,
                    message="Runtime restarted while job was active; marked FAILED for explicit retry",
                    reason_code="runtime_interrupted",
                    origin="runtime.recovery",
                )
                affected_job_files = self.job_files_repository.mark_in_progress_as_failed(
                    job.job_id,
                    "runtime_interrupted",
                )
                self.jobs_repository.events_repository.append_event(
                    job_id=job.job_id,
                    event_type="job.recovery_completed",
                    level="WARN",
                    origin="runtime.recovery",
                    message="Interrupted job normalized to FAILED",
                    payload={
                        "reason_code": "runtime_interrupted",
                        "affected_job_files": affected_job_files,
                        "removed_partial_files": removed_partial_files,
                    },
                )
                recovered.append(
                    {
                        "job_id": job.job_id,
                        "affected_job_files": affected_job_files,
                        "removed_partial_files": removed_partial_files,
                    }
                )
        return recovered

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
