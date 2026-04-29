"""Runtime-owned job execution orchestration."""

from __future__ import annotations

from pathlib import Path

from app.parsers.registry import default_registry
from app.persistence.db import Database
from app.persistence.models import Job, SystemVolume
from app.persistence.repositories import EventRepository, JobRepository
from app.runtime.lifecycle import JobLifecycleService
from app.runtime.offload import DestinationPlan, OffloadService
from app.runtime.parse import ParseService
from app.runtime.reports import ReportService
from app.runtime.state_machine import JobState
from app.runtime.volume_monitor import VolumeProvider


class JobRunnerError(RuntimeError):
    """Raised when a runtime job cannot be executed."""


class RuntimeJobRunner:
    """Connect queued API jobs to the runtime-only execution services."""

    def __init__(
        self,
        *,
        database: Database,
        lifecycle: JobLifecycleService,
        volume_provider: VolumeProvider,
    ) -> None:
        self.database = database
        self.lifecycle = lifecycle
        self.volume_provider = volume_provider

    def run(self, job_id: str) -> None:
        """Run one queued job through offload, parse, and report generation."""

        try:
            if not self._transition(job_id, JobState.SCANNING):
                return
            job = self._require_job(job_id)
            source_root, plan = self.resolve_job_paths(job)
            if not self._transition(job_id, JobState.PREPARING):
                return
            if not self._transition(job_id, JobState.COPYING):
                return
            offload = OffloadService(self.database).execute(
                job_id=job_id,
                source_root=source_root,
                plan=plan,
                finalize_state=False,
            )
            if offload.state is JobState.FAILED:
                self._transition(job_id, JobState.FAILED)
                return
            if not self._transition(job_id, JobState.VERIFYING):
                return
            if not self._transition(job_id, JobState.PARSING):
                return
            project_root = plan.main_project_root
            ParseService(self.database, default_registry()).parse_job(
                job_id,
                project_root / "01_footage",
            )
            if not self._transition(job_id, JobState.REPORTING):
                return
            ReportService(self.database).generate(
                job_id=job_id,
                project_root=project_root,
                frames_available=False,
            )
            self._transition(
                job_id,
                JobState.WARN if offload.state is JobState.WARN else JobState.COMPLETED,
            )
        except Exception as exc:
            self._record_failure(job_id, exc)

    def resolve_job_paths(self, job: Job) -> tuple[Path, DestinationPlan]:
        volumes = {volume.volume_id: volume for volume in self._volumes()}
        source = self._require_volume(volumes, job.source_volume_id, "source")
        main = self._require_volume(volumes, job.dest_main_id, "destination")
        backup = (
            self._require_volume(volumes, job.dest_backup_id, "destination")
            if job.dest_backup_id
            else None
        )
        return (
            Path(source.display_path),
            DestinationPlan(
                project_name=job.project_name,
                main_root=Path(main.display_path),
                backup_root=Path(backup.display_path) if backup else None,
            ),
        )

    def project_root_for_job(self, job: Job) -> Path:
        _, plan = self.resolve_job_paths(job)
        return plan.main_project_root

    def _require_job(self, job_id: str) -> Job:
        with self.database.session() as connection:
            job = JobRepository(connection).get(job_id)
        if job is None:
            raise JobRunnerError(f"job not found: {job_id}")
        return job

    def _transition(self, job_id: str, state: JobState) -> bool:
        return self.lifecycle.transition_job(job_id, state).accepted

    def _volumes(self) -> list[SystemVolume]:
        snapshot = self.volume_provider.scan()
        return snapshot.sources + snapshot.destinations

    def _require_volume(
        self,
        volumes: dict[str, SystemVolume],
        volume_id: str,
        kind: str,
    ) -> SystemVolume:
        volume = volumes.get(volume_id)
        if volume is None or volume.kind != kind:
            raise JobRunnerError(f"{kind} volume not found: {volume_id}")
        return volume

    def _record_failure(self, job_id: str, exc: Exception) -> None:
        with self.database.session() as connection:
            jobs = JobRepository(connection)
            events = EventRepository(connection)
            job = jobs.get(job_id)
            state_before = job.state if job else None
            if job is not None and JobState(job.state) not in {
                JobState.FAILED,
                JobState.CANCELLED,
                JobState.COMPLETED,
            }:
                jobs.update_state(job_id, JobState.FAILED, current_step="failed")
            events.append(
                "runtime_job_failed",
                job_id=job_id,
                state_before=state_before,
                state_after=JobState.FAILED.value,
                accepted=False,
                reason=str(exc),
            )
