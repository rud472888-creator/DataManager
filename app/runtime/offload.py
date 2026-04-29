"""Runtime-only offload and checksum pipeline."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.persistence.db import Database
from app.persistence.models import JobFile
from app.persistence.repositories import EventRepository, JobFileRepository, JobRepository
from app.runtime.checksum import sha256_file
from app.runtime.scan import ScannedFile, scan_source
from app.runtime.state_machine import JobState


class OffloadError(RuntimeError):
    """Raised for unrecoverable offload failures."""


@dataclass(frozen=True)
class DestinationPlan:
    project_name: str
    main_root: Path
    backup_root: Path | None

    @property
    def main_project_root(self) -> Path:
        return self.main_root / self.project_name

    @property
    def backup_project_root(self) -> Path | None:
        return self.backup_root / self.project_name if self.backup_root else None


@dataclass(frozen=True)
class OffloadResult:
    job_id: str
    state: JobState
    files: list[JobFile] = field(default_factory=list)
    reason: str = ""


def create_destination_scaffold(project_root: Path) -> None:
    for relpath in (
        Path("00_master/reports"),
        Path("00_master/manifests"),
        Path("00_master/logs"),
        Path("01_footage"),
    ):
        (project_root / relpath).mkdir(parents=True, exist_ok=True)


def target_for(project_root: Path, scanned_file: ScannedFile) -> Path:
    return project_root / "01_footage" / scanned_file.relpath


class OffloadService:
    """Copy and verify files from source to main/backup destinations."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def execute(
        self,
        *,
        job_id: str,
        source_root: Path,
        plan: DestinationPlan,
        finalize_state: bool = True,
    ) -> OffloadResult:
        try:
            scanned_files = scan_source(source_root)
        except OSError as exc:
            return self._fail_job(job_id, "source_unavailable", str(exc), finalize_state)
        if not scanned_files:
            return self._fail_job(
                job_id,
                "no_supported_files",
                "no supported files found",
                finalize_state,
            )
        try:
            self._prepare_destinations(plan, scanned_files)
        except OffloadError as exc:
            return self._fail_job(job_id, "destination_error", str(exc), finalize_state)

        results: list[JobFile] = []
        saw_backup_failure = False
        for scanned_file in scanned_files:
            result = self._copy_one(job_id, scanned_file, plan)
            results.append(result)
            if result.status == "failed":
                return self._finish_job(
                    job_id,
                    JobState.FAILED,
                    results,
                    result.error_code or "failed",
                    finalize_state,
                )
            if result.status == "warn":
                saw_backup_failure = True
        state = JobState.WARN if saw_backup_failure else JobState.COMPLETED
        reason = "backup failure" if saw_backup_failure else "offload verified"
        return self._finish_job(job_id, state, results, reason, finalize_state)

    def _prepare_destinations(
        self,
        plan: DestinationPlan,
        scanned_files: list[ScannedFile],
    ) -> None:
        create_destination_scaffold(plan.main_project_root)
        if plan.backup_project_root is not None:
            create_destination_scaffold(plan.backup_project_root)
        for scanned_file in scanned_files:
            targets = [target_for(plan.main_project_root, scanned_file)]
            if plan.backup_project_root is not None:
                targets.append(target_for(plan.backup_project_root, scanned_file))
            for target in targets:
                if target.exists():
                    raise OffloadError(f"target collision blocks overwrite: {target}")

    def _copy_one(self, job_id: str, scanned_file: ScannedFile, plan: DestinationPlan) -> JobFile:
        source_checksum = sha256_file(scanned_file.path)
        main_target = target_for(plan.main_project_root, scanned_file)
        backup_target = (
            target_for(plan.backup_project_root, scanned_file) if plan.backup_project_root else None
        )
        try:
            main_checksum = _copy_and_hash(scanned_file.path, main_target)
        except OSError as exc:
            return _job_file(
                job_id,
                scanned_file,
                status="failed",
                checksum_source=source_checksum,
                error_code="main_copy_failed",
                error_message=str(exc),
            )
        if main_checksum != source_checksum:
            return _job_file(
                job_id,
                scanned_file,
                status="failed",
                dest_main_relpath=_output_relpath(scanned_file),
                checksum_source=source_checksum,
                checksum_main=main_checksum,
                error_code="main_checksum_mismatch",
                error_message="main destination checksum mismatch",
            )

        backup_checksum: str | None = None
        backup_status = "verified"
        error_code: str | None = None
        error_message: str | None = None
        if backup_target is not None:
            try:
                backup_checksum = _copy_and_hash(scanned_file.path, backup_target)
                if backup_checksum != source_checksum:
                    backup_status = "warn"
                    error_code = "backup_checksum_mismatch"
                    error_message = "backup destination checksum mismatch"
            except OSError as exc:
                backup_status = "warn"
                error_code = "backup_copy_failed"
                error_message = str(exc)

        return _job_file(
            job_id,
            scanned_file,
            status=backup_status,
            dest_main_relpath=_output_relpath(scanned_file),
            dest_backup_relpath=_output_relpath(scanned_file) if backup_target else None,
            checksum_source=source_checksum,
            checksum_main=main_checksum,
            checksum_backup=backup_checksum,
            error_code=error_code,
            error_message=error_message,
        )

    def _fail_job(
        self,
        job_id: str,
        code: str,
        reason: str,
        finalize_state: bool,
    ) -> OffloadResult:
        return self._finish_job(job_id, JobState.FAILED, [], f"{code}: {reason}", finalize_state)

    def _finish_job(
        self,
        job_id: str,
        state: JobState,
        files: list[JobFile],
        reason: str,
        finalize_state: bool,
    ) -> OffloadResult:
        with self.database.session() as connection:
            jobs = JobRepository(connection)
            events = EventRepository(connection)
            file_repo = JobFileRepository(connection)
            for file_result in files:
                file_repo.upsert_result(file_result)
            job = jobs.get(job_id)
            if job is None:
                raise OffloadError(f"job not found: {job_id}")
            if finalize_state:
                jobs.update_state(job_id, state, current_step=state.value.lower())
            events.append(
                "offload_finished",
                job_id=job_id,
                state_before=job.state,
                state_after=state.value,
                accepted=True,
                reason=reason,
            )
        return OffloadResult(job_id=job_id, state=state, files=files, reason=reason)


def _copy_and_hash(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return sha256_file(target)


def _job_file(
    job_id: str,
    scanned_file: ScannedFile,
    *,
    status: str,
    dest_main_relpath: str | None = None,
    dest_backup_relpath: str | None = None,
    checksum_source: str | None = None,
    checksum_main: str | None = None,
    checksum_backup: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> JobFile:
    return JobFile(
        file_id=str(uuid5(NAMESPACE_URL, f"{job_id}:{scanned_file.relpath.as_posix()}")),
        job_id=job_id,
        source_relpath=scanned_file.relpath.as_posix(),
        dest_main_relpath=dest_main_relpath,
        dest_backup_relpath=dest_backup_relpath,
        size_bytes=scanned_file.size_bytes,
        checksum_source=checksum_source,
        checksum_main=checksum_main,
        checksum_backup=checksum_backup,
        status=status,
        error_code=error_code,
        error_message=error_message,
    )


def _output_relpath(scanned_file: ScannedFile) -> str:
    return (Path("01_footage") / scanned_file.relpath).as_posix()
