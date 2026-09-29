"""Runtime-only n:n replication and checksum pipeline."""

from __future__ import annotations

import re
import shutil
from contextlib import suppress
from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.persistence.db import Database
from app.persistence.models import JobFile, JobFileReplica
from app.persistence.repositories import EventRepository, JobFileRepository, JobRepository
from app.runtime.checksum import sha256_file
from app.runtime.scan import ScannedFile, scan_source
from app.runtime.state_machine import JobState


class OffloadError(RuntimeError):
    """Raised for unrecoverable replication failures."""


@dataclass(frozen=True)
class SourcePath:
    path_id: str
    root: Path


@dataclass(frozen=True)
class ReplicaPath:
    path_id: str
    root: Path


@dataclass(frozen=True)
class DestinationPlan:
    project_name: str
    replica_paths: tuple[ReplicaPath, ...]
    footage_run_name: str | None = None
    flat_card_layout: bool = False

    @property
    def project_roots(self) -> tuple[Path, ...]:
        return tuple(replica.root / self.project_name for replica in self.replica_paths)

    @property
    def report_project_root(self) -> Path:
        if not self.project_roots:
            raise OffloadError("at least one replica path is required")
        return self.project_roots[0]


PROJECT_FOLDERS = (
    Path("00_Master"),
    Path("01_Footage"),
    Path("02_Comp"),
    Path("03_2D_Design"),
    Path("04_Color"),
    Path("05_Sound"),
    Path("06_FIN"),
    Path("07_ETC_DATA"),
)
MASTER_SUBFOLDERS = (
    Path("00_Master/reports"),
    Path("00_Master/manifests"),
    Path("00_Master/logs"),
)
FOOTAGE_FOLDER = Path("01_Footage")
RUN_FOLDER_PATTERN = re.compile(r"^R#([1-9][0-9]*)$")


@dataclass(frozen=True)
class OffloadResult:
    job_id: str
    state: JobState
    files: list[JobFile] = field(default_factory=list)
    reason: str = ""


def create_destination_scaffold(project_root: Path, flat_card_layout: bool = False) -> None:
    folders = tuple(Path("001_Footage") if flat_card_layout and p == FOOTAGE_FOLDER else p for p in PROJECT_FOLDERS)
    for relpath in folders + MASTER_SUBFOLDERS:
        (project_root / relpath).mkdir(parents=True, exist_ok=True)


def target_for(
    project_root: Path,
    run_name: str,
    source_path_id: str,
    scanned_file: ScannedFile,
    flat_card_layout: bool = False,
) -> Path:
    if flat_card_layout:
        return project_root / "001_Footage" / run_name / scanned_file.relpath
    return project_root / _output_relpath(source_path_id, scanned_file, run_name)


def next_footage_run_name(plan: DestinationPlan) -> str:
    highest = 0
    for project_root in plan.project_roots:
        footage_root = project_root / ("001_Footage" if plan.flat_card_layout else FOOTAGE_FOLDER)
        if not footage_root.exists():
            continue
        for child in footage_root.iterdir():
            if not child.is_dir():
                continue
            match = RUN_FOLDER_PATTERN.match(child.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"R#{highest + 1}"


class OffloadService:
    """Copy and verify every source path into every equal replica path."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def execute(
        self,
        *,
        job_id: str,
        source_paths: tuple[SourcePath, ...],
        plan: DestinationPlan,
        finalize_state: bool = True,
    ) -> OffloadResult:
        if not source_paths:
            return self._fail_job(
                job_id,
                "no_source_paths",
                "at least one source path is required",
                finalize_state,
            )
        if plan.flat_card_layout and len(source_paths) != 1:
            return self._fail_job(job_id, "multiple_sources", "flat card layout requires one source", finalize_state)
        if not plan.replica_paths:
            return self._fail_job(
                job_id,
                "no_replica_paths",
                "at least one replica path is required",
                finalize_state,
            )
        try:
            scanned_by_source = [(source, scan_source(source.root)) for source in source_paths]
        except OSError as exc:
            return self._fail_job(job_id, "source_unavailable", str(exc), finalize_state)
        if not any(scanned_files for _, scanned_files in scanned_by_source):
            return self._fail_job(
                job_id,
                "no_supported_files",
                "no supported files found",
                finalize_state,
            )
        active_plan = replace(
            plan,
            footage_run_name=plan.footage_run_name or next_footage_run_name(plan),
        )
        try:
            self._prepare_destinations(active_plan, scanned_by_source)
        except OffloadError as exc:
            return self._fail_job(job_id, "destination_error", str(exc), finalize_state)

        results: list[JobFile] = []
        saw_warn = False
        for source, scanned_files in scanned_by_source:
            for scanned_file in scanned_files:
                result = self._copy_one(job_id, source, scanned_file, active_plan)
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
                    saw_warn = True
        state = JobState.WARN if saw_warn else JobState.COMPLETED
        reason = "replica failure" if saw_warn else "replication verified"
        return self._finish_job(job_id, state, results, reason, finalize_state)

    def _prepare_destinations(
        self,
        plan: DestinationPlan,
        scanned_by_source: list[tuple[SourcePath, list[ScannedFile]]],
    ) -> None:
        if plan.footage_run_name is None:
            raise OffloadError("footage run name was not resolved")
        for project_root in plan.project_roots:
            create_destination_scaffold(project_root, plan.flat_card_layout)
        for source, scanned_files in scanned_by_source:
            for scanned_file in scanned_files:
                for replica in plan.replica_paths:
                    target = target_for(
                        replica.root / plan.project_name,
                        plan.footage_run_name,
                        source.path_id,
                        scanned_file,
                        plan.flat_card_layout,
                    )
                    if target.exists() and target.stat().st_size != scanned_file.size_bytes:
                        raise OffloadError(f"target collision blocks overwrite: {target}")

    def _copy_one(
        self,
        job_id: str,
        source: SourcePath,
        scanned_file: ScannedFile,
        plan: DestinationPlan,
    ) -> JobFile:
        if plan.footage_run_name is None:
            raise OffloadError("footage run name was not resolved")
        source_checksum = sha256_file(scanned_file.path)
        replica_results: list[JobFileReplica] = []
        for replica in plan.replica_paths:
            project_root = replica.root / plan.project_name
            target = target_for(project_root, plan.footage_run_name, source.path_id, scanned_file, plan.flat_card_layout)
            replica_results.append(
                self._copy_to_replica(
                    source,
                    replica,
                    scanned_file,
                    target,
                    plan.footage_run_name,
                    source_checksum,
                    job_id,
                )
            )
        failed = [result for result in replica_results if result.status != "verified"]
        if any(result.error_code == "target_collision" for result in failed):
            status = "failed"
            error_code = "target_collision"
            error_message = "target collision blocks overwrite"
        elif len(failed) == len(replica_results):
            status = "failed"
            error_code = failed[0].error_code
            error_message = failed[0].error_message
        elif failed:
            status = "warn"
            error_code = "replica_incomplete"
            error_message = "one or more replica paths failed verification"
        else:
            status = "verified"
            error_code = None
            error_message = None
        return _job_file(
            job_id,
            source,
            scanned_file,
            status=status,
            checksum_source=source_checksum,
            replica_results=tuple(replica_results),
            error_code=error_code,
            error_message=error_message,
        )

    def _copy_to_replica(
        self,
        source: SourcePath,
        replica: ReplicaPath,
        scanned_file: ScannedFile,
        target: Path,
        run_name: str,
        source_checksum: str,
        job_id: str,
    ) -> JobFileReplica:
        file_id = _file_id(job_id, source, scanned_file)
        dest_relpath = Path(*target.relative_to(replica.root).parts[1:]).as_posix()
        if target.exists():
            try:
                checksum = sha256_file(target)
            except OSError as exc:
                return JobFileReplica(
                    file_id=file_id,
                    path_id=replica.path_id,
                    dest_relpath=dest_relpath,
                    checksum=None,
                    status="failed",
                    error_code="target_collision",
                    error_message=f"target collision blocks overwrite: {target}: {exc}",
                )
            if checksum == source_checksum:
                return JobFileReplica(
                    file_id=file_id,
                    path_id=replica.path_id,
                    dest_relpath=dest_relpath,
                    checksum=checksum,
                    status="verified",
                )
            return JobFileReplica(
                file_id=file_id,
                path_id=replica.path_id,
                dest_relpath=dest_relpath,
                checksum=checksum,
                status="failed",
                error_code="target_collision",
                error_message=f"target collision blocks overwrite: {target}",
            )
        try:
            checksum = _copy_and_hash(scanned_file.path, target)
        except OSError as exc:
            return JobFileReplica(
                file_id=file_id,
                path_id=replica.path_id,
                dest_relpath=dest_relpath,
                checksum=None,
                status="failed",
                error_code="replica_copy_failed",
                error_message=str(exc),
            )
        if checksum != source_checksum:
            return JobFileReplica(
                file_id=file_id,
                path_id=replica.path_id,
                dest_relpath=dest_relpath,
                checksum=checksum,
                status="failed",
                error_code="replica_checksum_mismatch",
                error_message="replica checksum mismatch",
            )
        return JobFileReplica(
            file_id=file_id,
            path_id=replica.path_id,
            dest_relpath=dest_relpath,
            checksum=checksum,
            status="verified",
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
    partial = target.with_name(f".{target.name}.partial-{uuid4().hex}")
    try:
        shutil.copyfile(source, partial)
        checksum = sha256_file(partial)
        _copy_metadata_best_effort(source, partial)
        partial.replace(target)
        return checksum
    except OSError:
        with suppress(OSError):
            partial.unlink()
        raise


def _copy_metadata_best_effort(source: Path, target: Path) -> None:
    try:
        shutil.copystat(source, target)
    except OSError:
        pass


def _job_file(
    job_id: str,
    source: SourcePath,
    scanned_file: ScannedFile,
    *,
    status: str,
    checksum_source: str | None = None,
    replica_results: tuple[JobFileReplica, ...] = (),
    error_code: str | None = None,
    error_message: str | None = None,
) -> JobFile:
    return JobFile(
        file_id=_file_id(job_id, source, scanned_file),
        job_id=job_id,
        source_path_id=source.path_id,
        source_relpath=scanned_file.relpath.as_posix(),
        size_bytes=scanned_file.size_bytes,
        checksum_source=checksum_source,
        replica_results=replica_results,
        status=status,
        error_code=error_code,
        error_message=error_message,
    )


def _file_id(job_id: str, source: SourcePath, scanned_file: ScannedFile) -> str:
    return str(uuid5(NAMESPACE_URL, f"{job_id}:{source.path_id}:{scanned_file.relpath.as_posix()}"))


def _output_relpath(source_path_id: str, scanned_file: ScannedFile, run_name: str) -> str:
    return (FOOTAGE_FOLDER / run_name / source_path_id / scanned_file.relpath).as_posix()
