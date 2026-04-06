from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.persistence.models import JobFileRecord, JobRecord, VolumeRecord
from app.persistence.repositories import PersistenceBundle
from app.runtime.checksum import ChecksumMismatchError, sha256_file
from app.runtime.commands import CommandResult
from app.runtime.dependencies import probe_runtime_dependencies
from app.runtime.events import EventBus, utc_now_iso
from app.runtime.offload import build_project_tree, copy_file_with_progress, partial_copy_path
from app.runtime.recovery import RecoveryManager
from app.runtime.scan import scan_source_volume
from app.runtime.scheduler import Scheduler
from app.runtime.state_machine import JobCommand, JobState, command_allowed
from app.runtime.volume_monitor import VolumeMonitor


@dataclass(slots=True)
class JobControl:
    cancel_requested: bool = False
    pause_requested: bool = False


class RuntimeAbort(Exception):
    """Internal signal for controlled stop paths like cancel/pause."""


class RuntimeAgent:
    """Local runtime authority for A2.

    The runtime owns all file discovery, destination preparation, copy work,
    state persistence, and event publication. The API layer only submits
    commands and reads runtime-owned state.
    """

    def __init__(self, settings: Settings, persistence: PersistenceBundle, event_bus: EventBus) -> None:
        self.settings = settings
        self.persistence = persistence
        self.event_bus = event_bus
        self.scheduler = Scheduler()
        self.recovery = RecoveryManager(self.persistence.jobs, self.persistence.job_files)
        self.volume_monitor = VolumeMonitor(self.persistence.volumes)
        self.dependencies = probe_runtime_dependencies()
        self.started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        self._stop_event = asyncio.Event()
        self._scheduler_task: asyncio.Task[None] | None = None
        self._current_job_task: asyncio.Task[None] | None = None
        self._controls: dict[str, JobControl] = {}
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        defaults = {
            "auth.token_hash": self.persistence.settings.hash_token(self.settings.token),
            "runtime.allowed_destination_roots": list(self.settings.allowed_destination_roots),
            "runtime.poll_interval_sec": 1,
            "runtime.default_checksum_algorithm": "sha256",
            "reports.output_root": str(self.settings.reports_dir),
        }
        self.persistence.settings.ensure_defaults(defaults)
        recovered = self.recovery.recover_interrupted_jobs()
        for item in recovered:
            await self.event_bus.publish(
                "job.recovery_notice",
                {
                    "message": "Job was active during previous shutdown and is now FAILED",
                    "affected_job_files": item["affected_job_files"],
                    "removed_partial_files": item["removed_partial_files"],
                },
                job_id=str(item["job_id"]),
            )
        self.refresh_volumes()
        self.refresh_scheduler()
        await self.event_bus.publish("runtime.status", self.runtime_status_payload())
        self._scheduler_task = asyncio.create_task(self._scheduler_loop(), name="fdm-scheduler")

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._current_job_task is not None:
            self._current_job_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._current_job_task
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task

    def refresh_scheduler(self) -> None:
        self.scheduler.sync_from_jobs(self.persistence.jobs.list_jobs())

    def refresh_volumes(self) -> list[VolumeRecord]:
        self.volume_monitor.refresh(self.settings.allowed_destination_roots)
        return self.persistence.volumes.list_volumes()

    def runtime_status_payload(self) -> dict[str, object]:
        jobs = self.persistence.jobs.list_jobs()
        queued = [job for job in jobs if job.state == JobState.QUEUED.value]
        return {
            "app_name": self.settings.app_name,
            "app_version": self.settings.app_version,
            "status": "ok",
            "started_at": self.started_at,
            "db_path": str(self.settings.db_path),
            "active_job_id": self.scheduler.active_job_id,
            "queue_depth": len(queued),
            "dependencies": self.dependencies,
            "stubbed_components": [
                "metadata_parse",
                "frame_capture",
                "reports",
            ],
        }

    def list_volumes(self) -> list[dict[str, object]]:
        return [
            {
                "volume_id": volume.volume_id,
                "display_name": volume.display_name,
                "mount_path": volume.mount_path,
                "volume_role": volume.volume_role,
                "approval_state": volume.approval_state,
                "free_bytes": volume.free_bytes,
                "capacity_bytes": volume.capacity_bytes,
            }
            for volume in self.persistence.volumes.list_volumes()
        ]

    def _serialize_job(self, job: JobRecord) -> dict[str, object]:
        return {
            "job_id": job.job_id,
            "retry_of_job_id": job.retry_of_job_id,
            "project_name": job.project_name,
            "source_volume_id": job.source_volume_id,
            "dest_main_id": job.dest_main_id,
            "dest_backup_id": job.dest_backup_id,
            "state": job.state,
            "current_step": job.current_step,
            "resume_step": job.resume_step,
            "operator_origin": job.operator_origin,
            "policy": job.policy(),
            "stats": job.stats(),
            "warning_count": job.warning_count,
            "error_count": job.error_count,
            "current_file_relpath": job.current_file_relpath,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "ended_at": job.ended_at,
            "last_event_id": job.last_event_id,
        }

    def list_jobs(self) -> list[dict[str, object]]:
        return [self._serialize_job(job) for job in self.persistence.jobs.list_jobs()]

    def get_job(self, job_id: str) -> dict[str, object] | None:
        job = self.persistence.jobs.get_job(job_id)
        return self._serialize_job(job) if job else None

    def _validate_source_and_destinations(
        self,
        *,
        source_volume_id: str,
        dest_main_id: str,
        dest_backup_id: str | None,
    ) -> None:
        source = self.persistence.volumes.get_volume(source_volume_id)
        if source is None or source.volume_role != "source":
            raise ValueError("source_volume_id must reference a runtime-detected source volume")
        main = self.persistence.volumes.get_volume(dest_main_id)
        if main is None or main.volume_role != "destination":
            raise ValueError("dest_main_id must reference an approved destination volume")
        if dest_backup_id is not None:
            backup = self.persistence.volumes.get_volume(dest_backup_id)
            if backup is None or backup.volume_role != "destination":
                raise ValueError("dest_backup_id must reference an approved destination volume")

    async def create_job(
        self,
        *,
        project_name: str,
        source_volume_id: str,
        dest_main_id: str,
        dest_backup_id: str | None,
        policy: Mapping[str, object],
        origin: str,
    ) -> dict[str, object]:
        self._validate_source_and_destinations(
            source_volume_id=source_volume_id,
            dest_main_id=dest_main_id,
            dest_backup_id=dest_backup_id,
        )
        job_id = f"JOB-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        job = self.persistence.jobs.create_job(
            {
                "job_id": job_id,
                "retry_of_job_id": None,
                "project_name": project_name,
                "source_volume_id": source_volume_id,
                "dest_main_id": dest_main_id,
                "dest_backup_id": dest_backup_id,
                "state": JobState.QUEUED.value,
                "current_step": "queued",
                "resume_step": None,
                "operator_origin": origin,
                "policy_json": dict(policy),
                "stats_json": {
                    "processed_files": 0,
                    "total_files": 0,
                    "bytes_done": 0,
                    "bytes_total": 0,
                    "speed_mbps": 0.0,
                    "eta_sec": None,
                    "warnings": 0,
                    "errors": 0,
                    "message": "Queued",
                },
                "warning_count": 0,
                "error_count": 0,
                "current_file_relpath": None,
            }
        )
        self.refresh_scheduler()
        serialized = self._serialize_job(job)
        await self.event_bus.publish("job.created", serialized, job_id=job.job_id)
        return serialized

    async def handle_command(self, *, job_id: str, command_name: str, origin: str) -> CommandResult:
        job = self.persistence.jobs.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        command = JobCommand(command_name)
        state = JobState(job.state)
        allowed, reason = command_allowed(state, command)
        if not allowed:
            event_id = self.persistence.jobs.append_command_result(
                job_id=job_id,
                command=command,
                accepted=False,
                message=reason,
                origin=origin,
                payload={"state": state.value},
            )
            await self.event_bus.publish(
                "job.command_result",
                {
                    "command": command.value,
                    "accepted": False,
                    "message": reason,
                    "persisted_event_id": event_id,
                },
                job_id=job_id,
            )
            return CommandResult(job_id, command.value, False, reason, event_id)

        accepted = True
        message = "Command accepted and recorded"
        if command is JobCommand.CANCEL and state in (JobState.QUEUED, JobState.PAUSED):
            self.persistence.jobs.transition_job_state(
                job_id=job_id,
                new_state=JobState.CANCELLED,
                current_step="cancelled",
                message="Job cancelled by operator request",
                origin=origin,
            )
            self.scheduler.clear_active_if_matches(job_id)
            message = "Command accepted; job cancelled"
        elif command is JobCommand.CANCEL:
            self._controls.setdefault(job_id, JobControl()).cancel_requested = True
            message = "Command accepted; runtime will cancel the active job"
        elif command is JobCommand.PAUSE:
            self._controls.setdefault(job_id, JobControl()).pause_requested = True
            message = "Command accepted; runtime will pause after the current file boundary"
        elif command is JobCommand.RESUME and state is JobState.PAUSED:
            if self.scheduler.can_accept_active_work():
                self.scheduler.mark_active(job_id)
                self._controls[job_id] = JobControl()
                self._current_job_task = asyncio.create_task(
                    self._run_job(job_id, resume_from_copy=True),
                    name=f"fdm-job-{job_id}-resume",
                )
                message = "Command accepted; job resumed"
            else:
                accepted = False
                message = "Resume rejected because another active job is already running"
        elif command is JobCommand.RETRY:
            retry_job = self.persistence.jobs.clone_job_for_retry(job_id, origin)
            message = f"Command accepted; retry job {retry_job.job_id} created"
        else:
            accepted = False
            message = f"Command {command.value} is not implemented for the current runtime slice"

        event_id = self.persistence.jobs.append_command_result(
            job_id=job_id,
            command=command,
            accepted=accepted,
            message=message,
            origin=origin,
            payload={"state": state.value},
        )
        await self.event_bus.publish(
            "job.command_result",
            {
                "command": command.value,
                "accepted": accepted,
                "message": message,
                "persisted_event_id": event_id,
            },
            job_id=job_id,
        )
        return CommandResult(job_id, command.value, accepted, message, event_id)

    async def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            await self._tick_scheduler()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=0.25)
            except TimeoutError:
                continue

    async def _tick_scheduler(self) -> None:
        async with self._lock:
            if self._current_job_task and self._current_job_task.done():
                with contextlib.suppress(RuntimeAbort, Exception):
                    self._current_job_task.result()
                self._current_job_task = None
            self.refresh_scheduler()
            if self._current_job_task is not None or not self.scheduler.can_accept_active_work():
                return
            next_job = self.persistence.jobs.get_next_queued_job()
            if next_job is None:
                return
            self.scheduler.mark_active(next_job.job_id)
            self._controls[next_job.job_id] = JobControl()
            self._current_job_task = asyncio.create_task(
                self._run_job(next_job.job_id, resume_from_copy=False),
                name=f"fdm-job-{next_job.job_id}",
            )

    async def _run_job(self, job_id: str, *, resume_from_copy: bool) -> None:
        try:
            if resume_from_copy:
                await self._transition_and_publish(
                    job_id=job_id,
                    new_state=JobState.COPYING,
                    current_step="copying",
                    message="Runtime resumed copy execution",
                    origin="runtime.worker",
                )
                prepared = await self._load_prepared_paths(job_id)
                if prepared is None:
                    raise RuntimeError("Resume metadata is missing for paused job")
                outcome = await self._copy_job(job_id, prepared)
            else:
                await self._transition_and_publish(
                    job_id=job_id,
                    new_state=JobState.SCANNING,
                    current_step="scanning",
                    message="Runtime started local source scan",
                    origin="runtime.worker",
                    started_at=utc_now_iso(),
                )
                scanned = await self._scan_job(job_id)
                await self._check_cancel_before_stage(job_id)
                await self._transition_and_publish(
                    job_id=job_id,
                    new_state=JobState.PREPARING,
                    current_step="preparing",
                    message="Runtime preparing destination structures",
                    origin="runtime.worker",
                )
                prepared = await self._prepare_job(job_id, scanned)
                await self._check_cancel_before_stage(job_id)
                await self._transition_and_publish(
                    job_id=job_id,
                    new_state=JobState.COPYING,
                    current_step="copying",
                    message="Runtime started local byte copy",
                    origin="runtime.worker",
                )
                outcome = await self._copy_job(job_id, prepared)

            if outcome in {"paused", "cancelled"}:
                return

            await self._transition_and_publish(
                job_id=job_id,
                new_state=JobState.VERIFYING,
                current_step="verifying",
                message="Copy completed; runtime started checksum verification",
                origin="runtime.worker",
            )
            verification = await self._verify_job(job_id, prepared)
            if verification == "cancelled":
                return
            warning_reason = self._verification_warning_reason(job_id)
            await self._transition_and_publish(
                job_id=job_id,
                new_state=JobState.WARN,
                current_step="verified_pending_downstream",
                message=warning_reason,
                origin="runtime.worker",
            )
        except RuntimeAbort:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.persistence.job_files.mark_in_progress_as_failed(job_id, "runtime_exception")
            self.persistence.jobs.transition_job_state(
                job_id=job_id,
                new_state=JobState.FAILED,
                current_step="failed",
                message=f"Runtime worker failed: {exc}",
                origin="runtime.worker",
                reason_code="runtime_exception",
            )
            await self.event_bus.publish(
                "job.state_changed",
                {"state": JobState.FAILED.value, "message": str(exc)},
                job_id=job_id,
            )
        finally:
            self.scheduler.clear_active_if_matches(job_id)
            self._controls.pop(job_id, None)

    async def _scan_job(self, job_id: str) -> dict[str, object]:
        job = self.persistence.jobs.get_job(job_id)
        assert job is not None
        source_volume = self.persistence.volumes.get_volume(job.source_volume_id)
        assert source_volume is not None
        source_root = Path(source_volume.mount_path)
        files = scan_source_volume(source_root)
        persisted_files = self.persistence.job_files.replace_for_job(
            job_id,
            [{**file, "has_backup": job.dest_backup_id is not None} for file in files],
        )
        manifest_path = self.settings.data_dir / "jobs" / job_id / "scan_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "source_root": str(source_root),
                    "files": [record.relative_path for record in persisted_files],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        stats = job.stats()
        stats.update(
            {
                "total_files": len(persisted_files),
                "processed_files": 0,
                "bytes_total": sum(record.size_bytes for record in persisted_files),
                "bytes_done": 0,
                "speed_mbps": 0.0,
                "eta_sec": None,
                "warnings": 0,
                "errors": 0,
                "message": "Scan manifest created",
                "scan_manifest_path": str(manifest_path),
            }
        )
        self.persistence.jobs.update_job_runtime_fields(
            job_id=job_id,
            stats=stats,
            current_step="scanning",
            current_file_relpath="",
        )
        await self.event_bus.publish(
            "job.progress",
            {
                "state": JobState.SCANNING.value,
                "current_file": None,
                "processed_files": 0,
                "total_files": len(persisted_files),
                "bytes_done": 0,
                "bytes_total": stats["bytes_total"],
                "speed_mbps": 0.0,
                "eta_sec": None,
                "warnings": 0,
                "errors": 0,
                "message": "Scan manifest created",
            },
            job_id=job_id,
        )
        return {"source_root": source_root, "files": persisted_files}

    async def _prepare_job(self, job_id: str, scan_result: dict[str, object]) -> dict[str, object]:
        job = self.persistence.jobs.get_job(job_id)
        assert job is not None
        source_volume = self.persistence.volumes.get_volume(job.source_volume_id)
        main_volume = self.persistence.volumes.get_volume(job.dest_main_id)
        assert source_volume is not None and main_volume is not None
        project_name = self._sanitize_project_name(job.project_name)
        source_label = self._sanitize_project_name(source_volume.display_name)
        main_paths = build_project_tree(Path(main_volume.mount_path), project_name, source_label)
        backup_paths: dict[str, str] | None = None
        if job.dest_backup_id is not None:
            backup_volume = self.persistence.volumes.get_volume(job.dest_backup_id)
            assert backup_volume is not None
            backup_paths = {
                key: str(value)
                for key, value in build_project_tree(
                    Path(backup_volume.mount_path), project_name, source_label
                ).items()
            }
        stats = job.stats()
        stats.update(
            {
                "project_name_sanitized": project_name,
                "source_label": source_label,
                "main_paths": {key: str(value) for key, value in main_paths.items()},
                "backup_paths": backup_paths,
            }
        )
        self.persistence.jobs.update_job_runtime_fields(
            job_id=job_id,
            stats=stats,
            current_step="preparing",
        )
        await self.event_bus.publish(
            "job.state_changed",
            {"state": JobState.PREPARING.value, "message": "Destination directories prepared"},
            job_id=job_id,
        )
        return {
            "source_root": scan_result["source_root"],
            "files": scan_result["files"],
            "main_paths": {key: str(value) for key, value in main_paths.items()},
            "backup_paths": backup_paths,
        }

    async def _load_prepared_paths(self, job_id: str) -> dict[str, object] | None:
        job = self.persistence.jobs.get_job(job_id)
        if job is None:
            return None
        stats = job.stats()
        source_volume = self.persistence.volumes.get_volume(job.source_volume_id)
        if source_volume is None:
            return None
        main_paths = stats.get("main_paths")
        if not isinstance(main_paths, dict):
            return None
        return {
            "source_root": Path(source_volume.mount_path),
            "files": self.persistence.job_files.list_copy_pending(job_id),
            "main_paths": main_paths,
            "backup_paths": stats.get("backup_paths"),
        }

    async def _copy_job(self, job_id: str, prepared: dict[str, object]) -> str:
        job = self.persistence.jobs.get_job(job_id)
        assert job is not None
        files: list[JobFileRecord] = self.persistence.job_files.list_copy_pending(job_id)
        source_root = Path(prepared["source_root"])
        main_footage_root = Path(prepared["main_paths"]["footage_root"])
        backup_footage_root = (
            Path(prepared["backup_paths"]["footage_root"])
            if prepared["backup_paths"] is not None
            else None
        )
        initial_stats = job.stats()
        total_files = int(initial_stats.get("total_files", len(files)))
        total_bytes = int(initial_stats.get("bytes_total", sum(file.size_bytes for file in files)))
        already_copied = max(total_files - len(files), 0)
        bytes_done_total = max(total_bytes - sum(file.size_bytes for file in files), 0)
        warning_count = job.warning_count
        error_count = job.error_count
        started = time.monotonic()

        for file_record in files:
            control = self._controls.setdefault(job_id, JobControl())
            if control.cancel_requested:
                await self._cancel_running_job(job_id)
                return "cancelled"

            source_path = source_root / file_record.relative_path
            current_relpath = file_record.relative_path
            main_destination = main_footage_root / current_relpath
            backup_destination = backup_footage_root / current_relpath if backup_footage_root else None
            file_metadata = {
                **file_record.metadata(),
                "source_path": str(source_path),
                "main_destination": str(main_destination),
                "backup_destination": str(backup_destination) if backup_destination else None,
                "main_temp_path": str(partial_copy_path(main_destination)),
                "backup_temp_path": (
                    str(partial_copy_path(backup_destination)) if backup_destination else None
                ),
            }
            self.persistence.jobs.update_job_runtime_fields(
                job_id=job_id,
                current_step="copying",
                current_file_relpath=current_relpath,
            )
            self.persistence.job_files.update_copy_state(
                job_file_id=file_record.job_file_id,
                main_state="IN_PROGRESS",
                backup_state="IN_PROGRESS" if backup_footage_root is not None else "SKIPPED",
                warning_code=None,
                error_code=None,
                metadata=file_metadata,
            )

            async def publish_progress(file_bytes_done: int, elapsed_sec: float) -> None:
                total_done = bytes_done_total + file_bytes_done
                bytes_per_sec = total_done / max(time.monotonic() - started, 0.001)
                eta_sec = int(max(total_bytes - total_done, 0) / max(bytes_per_sec, 1))
                payload = {
                    "state": JobState.COPYING.value,
                    "current_file": current_relpath,
                    "processed_files": already_copied,
                    "total_files": total_files,
                    "bytes_done": total_done,
                    "bytes_total": total_bytes,
                    "speed_mbps": round((file_bytes_done / 1024 / 1024) / max(elapsed_sec, 0.001), 2),
                    "eta_sec": eta_sec,
                    "warnings": warning_count,
                    "errors": error_count,
                    "message": "Copying file",
                }
                self.persistence.jobs.update_job_runtime_fields(
                    job_id=job_id,
                    stats=payload,
                    current_step="copying",
                    current_file_relpath=current_relpath,
                    warning_count=warning_count,
                    error_count=error_count,
                )
                await self.event_bus.publish("job.progress", payload, job_id=job_id)

            try:
                await copy_file_with_progress(
                    source_path=source_path,
                    destination_path=main_destination,
                    progress_callback=publish_progress,
                    cancel_check=lambda: self._controls.get(job_id, JobControl()).cancel_requested,
                )
            except asyncio.CancelledError:
                await self._cancel_running_job(job_id)
                return "cancelled"
            except Exception as exc:
                self.persistence.job_files.update_copy_state(
                    job_file_id=file_record.job_file_id,
                    main_state="FAILED",
                    error_code="copy_main_failed",
                )
                self.persistence.events.append_event(
                    job_id=job_id,
                    event_type="job.file_result",
                    level="ERROR",
                    origin="runtime.copy",
                    message=f"Main copy failed for {current_relpath}: {exc}",
                    payload={"relative_path": current_relpath},
                    reason_code="copy_main_failed",
                )
                raise

            backup_state = "SKIPPED"
            if backup_footage_root is not None:
                try:
                    await copy_file_with_progress(
                        source_path=source_path,
                        destination_path=backup_destination,
                        progress_callback=publish_progress,
                        cancel_check=lambda: self._controls.get(job_id, JobControl()).cancel_requested,
                    )
                    backup_state = "COPIED"
                except asyncio.CancelledError:
                    await self._cancel_running_job(job_id)
                    return "cancelled"
                except Exception as exc:
                    backup_state = "FAILED"
                    warning_count += 1
                    backup_reason = "copy_backup_failed"
                    self.persistence.events.append_event(
                        job_id=job_id,
                        event_type="job.file_result",
                        level="WARN",
                        origin="runtime.copy",
                        message=f"Backup copy failed for {current_relpath}: {exc}",
                        payload={"relative_path": current_relpath},
                        reason_code=backup_reason,
                    )
                else:
                    backup_reason = None
            else:
                backup_reason = None

            already_copied += 1
            bytes_done_total += file_record.size_bytes
            self.persistence.job_files.update_copy_state(
                job_file_id=file_record.job_file_id,
                main_state="COPIED",
                backup_state=backup_state,
                warning_code=backup_reason,
                error_code=None,
                metadata=file_metadata,
            )
            self.persistence.events.append_event(
                job_id=job_id,
                event_type="job.file_result",
                level="INFO" if backup_state != "FAILED" else "WARN",
                origin="runtime.copy",
                message=f"Copied {current_relpath}",
                payload={
                    "relative_path": current_relpath,
                    "copy_main_state": "COPIED",
                    "copy_backup_state": backup_state,
                },
            )
            payload = {
                "state": JobState.COPYING.value,
                "current_file": current_relpath,
                "processed_files": already_copied,
                "total_files": total_files,
                "bytes_done": bytes_done_total,
                "bytes_total": total_bytes,
                "speed_mbps": round((bytes_done_total / 1024 / 1024) / max(time.monotonic() - started, 0.001), 2),
                "eta_sec": 0 if already_copied >= total_files else None,
                "warnings": warning_count,
                "errors": error_count,
                "message": "File copied",
            }
            self.persistence.jobs.update_job_runtime_fields(
                job_id=job_id,
                stats=payload,
                current_step="copying",
                current_file_relpath=current_relpath,
                warning_count=warning_count,
                error_count=error_count,
            )
            await self.event_bus.publish("job.progress", payload, job_id=job_id)

            control = self._controls.get(job_id, JobControl())
            if control.cancel_requested:
                await self._cancel_running_job(job_id)
                return "cancelled"
            if control.pause_requested:
                self.persistence.jobs.transition_job_state(
                    job_id=job_id,
                    new_state=JobState.PAUSING,
                    current_step="pausing",
                    message="Pause requested; pausing at a safe file boundary",
                    origin="runtime.copy",
                )
                await self.event_bus.publish(
                    "job.state_changed",
                    {"state": JobState.PAUSING.value, "message": "Pause requested"},
                    job_id=job_id,
                )
                self.persistence.jobs.transition_job_state(
                    job_id=job_id,
                    new_state=JobState.PAUSED,
                    current_step="paused",
                    message="Job paused at a copy boundary",
                    origin="runtime.copy",
                )
                await self.event_bus.publish(
                    "job.state_changed",
                    {"state": JobState.PAUSED.value, "message": "Job paused"},
                    job_id=job_id,
                )
                return "paused"

        return "completed"

    async def _verify_job(self, job_id: str, prepared: dict[str, object]) -> str:
        job = self.persistence.jobs.get_job(job_id)
        assert job is not None
        files = self.persistence.job_files.list_verify_pending(job_id)
        source_root = Path(prepared["source_root"])
        main_footage_root = Path(prepared["main_paths"]["footage_root"])
        backup_footage_root = (
            Path(prepared["backup_paths"]["footage_root"])
            if prepared["backup_paths"] is not None
            else None
        )
        total_files = len(files)
        total_bytes = sum(
            file.size_bytes * (2 + (1 if file.copy_backup_state == "COPIED" else 0))
            for file in files
        )
        processed_files = 0
        bytes_done_total = 0
        warning_count = job.warning_count
        error_count = job.error_count
        started = time.monotonic()

        for file_record in files:
            control = self._controls.setdefault(job_id, JobControl())
            if control.cancel_requested:
                await self._cancel_running_job(job_id)
                return "cancelled"

            source_path = source_root / file_record.relative_path
            main_destination = main_footage_root / file_record.relative_path
            backup_destination = (
                backup_footage_root / file_record.relative_path
                if backup_footage_root is not None
                else None
            )
            current_relpath = file_record.relative_path
            file_metadata = {
                **file_record.metadata(),
                "verify_source_path": str(source_path),
                "verify_main_path": str(main_destination),
                "verify_backup_path": str(backup_destination) if backup_destination else None,
            }
            self.persistence.jobs.update_job_runtime_fields(
                job_id=job_id,
                current_step="verifying",
                current_file_relpath=current_relpath,
            )
            self.persistence.job_files.update_verify_state(
                job_file_id=file_record.job_file_id,
                verify_main_state="IN_PROGRESS",
                verify_backup_state=(
                    "FAILED"
                    if file_record.copy_backup_state == "FAILED"
                    else "SKIPPED" if backup_destination is None else file_record.verify_backup_state
                ),
                warning_code=file_record.warning_code,
                error_code=None,
                metadata=file_metadata,
            )

            source_checksum: str | None = None
            main_checksum: str | None = None
            try:
                source_checksum = await sha256_file(
                    source_path,
                    cancel_check=lambda: self._controls.get(job_id, JobControl()).cancel_requested,
                )
                main_checksum = await sha256_file(
                    main_destination,
                    cancel_check=lambda: self._controls.get(job_id, JobControl()).cancel_requested,
                )
                if source_checksum != main_checksum:
                    raise ChecksumMismatchError(
                        path=main_destination,
                        expected=source_checksum,
                        actual=main_checksum,
                    )
            except asyncio.CancelledError:
                await self._cancel_running_job(job_id)
                return "cancelled"
            except FileNotFoundError as exc:
                error_count += 1
                self.persistence.job_files.update_verify_state(
                    job_file_id=file_record.job_file_id,
                    source_checksum_sha256=source_checksum,
                    main_checksum_sha256=main_checksum,
                    verify_main_state="FAILED",
                    verify_backup_state="SKIPPED",
                    error_code="verify_main_missing",
                    metadata=file_metadata,
                )
                self.persistence.events.append_event(
                    job_id=job_id,
                    event_type="job.file_result",
                    level="ERROR",
                    origin="runtime.verify",
                    message=f"Main verification missing file for {current_relpath}: {exc}",
                    payload={"relative_path": current_relpath},
                    reason_code="verify_main_missing",
                )
                raise RuntimeError(f"Main verification failed for {current_relpath}") from exc
            except ChecksumMismatchError as exc:
                error_count += 1
                self.persistence.job_files.update_verify_state(
                    job_file_id=file_record.job_file_id,
                    source_checksum_sha256=source_checksum,
                    main_checksum_sha256=main_checksum,
                    verify_main_state="FAILED",
                    verify_backup_state="SKIPPED",
                    error_code="verify_main_mismatch",
                    metadata=file_metadata,
                )
                self.persistence.events.append_event(
                    job_id=job_id,
                    event_type="job.file_result",
                    level="ERROR",
                    origin="runtime.verify",
                    message=str(exc),
                    payload={"relative_path": current_relpath},
                    reason_code="verify_main_mismatch",
                )
                raise RuntimeError(f"Main verification failed for {current_relpath}") from exc

            backup_state = "SKIPPED"
            backup_checksum: str | None = None
            warning_code = file_record.warning_code
            if file_record.copy_backup_state == "FAILED":
                backup_state = "FAILED"
                warning_code = warning_code or "copy_backup_failed"
            elif backup_destination is not None:
                self.persistence.job_files.update_verify_state(
                    job_file_id=file_record.job_file_id,
                    verify_backup_state="IN_PROGRESS",
                    metadata=file_metadata,
                )
                try:
                    backup_checksum = await sha256_file(
                        backup_destination,
                        cancel_check=lambda: self._controls.get(job_id, JobControl()).cancel_requested,
                    )
                    if source_checksum != backup_checksum:
                        backup_state = "FAILED"
                        warning_code = "verify_backup_mismatch"
                        warning_count += 1
                    else:
                        backup_state = "VERIFIED"
                except asyncio.CancelledError:
                    await self._cancel_running_job(job_id)
                    return "cancelled"
                except FileNotFoundError as exc:
                    backup_state = "FAILED"
                    warning_code = "verify_backup_missing"
                    warning_count += 1
                    self.persistence.events.append_event(
                        job_id=job_id,
                        event_type="job.file_result",
                        level="WARN",
                        origin="runtime.verify",
                        message=f"Backup verification missing file for {current_relpath}: {exc}",
                        payload={"relative_path": current_relpath},
                        reason_code="verify_backup_missing",
                    )

            self.persistence.job_files.update_verify_state(
                job_file_id=file_record.job_file_id,
                source_checksum_sha256=source_checksum,
                main_checksum_sha256=main_checksum,
                backup_checksum_sha256=backup_checksum,
                verify_main_state="VERIFIED",
                verify_backup_state=backup_state,
                warning_code=warning_code,
                metadata=file_metadata,
            )
            if backup_state == "FAILED" and warning_code in {"verify_backup_mismatch", "verify_backup_missing"}:
                self.persistence.events.append_event(
                    job_id=job_id,
                    event_type="job.file_result",
                    level="WARN",
                    origin="runtime.verify",
                    message=f"Backup verification warning for {current_relpath}",
                    payload={
                        "relative_path": current_relpath,
                        "verify_backup_state": backup_state,
                    },
                    reason_code=warning_code,
                )
            self.persistence.events.append_event(
                job_id=job_id,
                event_type="job.file_result",
                level="INFO" if backup_state != "FAILED" else "WARN",
                origin="runtime.verify",
                message=f"Verified {current_relpath}",
                payload={
                    "relative_path": current_relpath,
                    "verify_main_state": "VERIFIED",
                    "verify_backup_state": backup_state,
                },
            )

            processed_files += 1
            bytes_done_total += file_record.size_bytes * (
                2 + (1 if file_record.copy_backup_state == "COPIED" else 0)
            )
            payload = {
                "state": JobState.VERIFYING.value,
                "current_file": current_relpath,
                "processed_files": processed_files,
                "total_files": total_files,
                "bytes_done": bytes_done_total,
                "bytes_total": total_bytes,
                "speed_mbps": round(
                    (bytes_done_total / 1024 / 1024) / max(time.monotonic() - started, 0.001),
                    2,
                ),
                "eta_sec": 0 if processed_files >= total_files else None,
                "warnings": warning_count,
                "errors": error_count,
                "message": "File verified",
            }
            self.persistence.jobs.update_job_runtime_fields(
                job_id=job_id,
                stats=payload,
                current_step="verifying",
                current_file_relpath=current_relpath,
                warning_count=warning_count,
                error_count=error_count,
            )
            await self.event_bus.publish("job.progress", payload, job_id=job_id)

        return "completed"

    def _verification_warning_reason(self, job_id: str) -> str:
        has_backup_warning = any(
            record.warning_code in {"copy_backup_failed", "verify_backup_missing", "verify_backup_mismatch"}
            or record.verify_backup_state == "FAILED"
            for record in self.persistence.job_files.list_for_job(job_id)
        )
        if has_backup_warning:
            return "Verification completed with backup warnings; parse/capture/report remain stubbed in A2"
        return "Verification completed; parse/capture/report remain stubbed in A2"

    async def _cancel_running_job(self, job_id: str) -> None:
        self.persistence.job_files.mark_in_progress_as_failed(job_id, "cancelled")
        self.persistence.jobs.transition_job_state(
            job_id=job_id,
            new_state=JobState.CANCELLED,
            current_step="cancelled",
            message="Job cancelled during runtime execution",
            origin="runtime.worker",
        )
        await self.event_bus.publish(
            "job.state_changed",
            {"state": JobState.CANCELLED.value, "message": "Job cancelled"},
            job_id=job_id,
        )

    async def _check_cancel_before_stage(self, job_id: str) -> None:
        control = self._controls.get(job_id)
        if control and control.cancel_requested:
            await self._cancel_running_job(job_id)
            raise RuntimeAbort

    async def _transition_and_publish(
        self,
        *,
        job_id: str,
        new_state: JobState,
        current_step: str,
        message: str,
        origin: str,
        started_at: str | None = None,
    ) -> None:
        self.persistence.jobs.transition_job_state(
            job_id=job_id,
            new_state=new_state,
            current_step=current_step,
            message=message,
            origin=origin,
        )
        self.persistence.jobs.update_job_runtime_fields(
            job_id=job_id,
            current_step=current_step,
            started_at=started_at,
        )
        await self.event_bus.publish(
            "job.state_changed",
            {"state": new_state.value, "message": message},
            job_id=job_id,
        )

    @staticmethod
    def _sanitize_project_name(raw: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in raw.strip())
        return cleaned or "untitled_project"
