"""Repository boundaries for runtime persistence."""

from __future__ import annotations

import json
import sqlite3
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.persistence.models import (
    Clip,
    Job,
    JobEvent,
    JobFile,
    JobFileReplica,
    Report,
    SettingRecord,
    SystemVolume,
)
from app.runtime.state_machine import RECOVERABLE_STATES, JobState


class JobRepository:
    """Persistence operations for jobs."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_job(
        self,
        *,
        project_name: str,
        source_path_ids: tuple[str, ...],
        replica_path_ids: tuple[str, ...],
        operator_origin: str,
        policy: dict[str, object] | None = None,
    ) -> Job:
        job = Job(
            job_id=f"JOB-{uuid4().hex[:12]}",
            project_name=project_name,
            source_path_ids=source_path_ids,
            replica_path_ids=replica_path_ids,
            state="QUEUED",
            operator_origin=operator_origin,
            policy_json=json.dumps(policy or {}),
        )
        self.connection.execute(
            """
            INSERT INTO jobs (
              job_id, project_name, source_path_ids_json, replica_path_ids_json,
              state, operator_origin, policy_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                job.project_name,
                json.dumps(list(job.source_path_ids)),
                json.dumps(list(job.replica_path_ids)),
                job.state,
                job.operator_origin,
                job.policy_json,
            ),
        )
        return job

    def create_stub_job(self, project_name: str = "Foundation Job") -> Job:
        return self.create_job(
            project_name=project_name,
            source_path_ids=("mock-source",),
            replica_path_ids=("path1", "path2"),
            operator_origin="local_runtime",
        )

    def get(self, job_id: str) -> Job | None:
        row = self.connection.execute(
            """
            SELECT job_id, project_name, source_path_ids_json, replica_path_ids_json,
                   state, operator_origin, current_step, stats_json, policy_json,
                   recovery_cursor_json
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        return _job_from_row(row) if row else None

    def list_all(self) -> list[Job]:
        rows = self.connection.execute(
            """
            SELECT job_id, project_name, source_path_ids_json, replica_path_ids_json,
                   state, operator_origin, current_step, stats_json, policy_json,
                   recovery_cursor_json
            FROM jobs
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [_job_from_row(row) for row in rows]

    def active_job_id(self) -> str | None:
        row = self.connection.execute(
            """
            SELECT job_id FROM jobs
            WHERE state NOT IN ('WARN', 'FAILED', 'CANCELLED', 'COMPLETED')
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        return str(row["job_id"]) if row else None

    def update_state(
        self,
        job_id: str,
        state: JobState,
        *,
        current_step: str | None = None,
    ) -> Job:
        self.connection.execute(
            """
            UPDATE jobs
            SET state = ?, current_step = ?
            WHERE job_id = ?
            """,
            (state.value, current_step, job_id),
        )
        job = self.get(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        return job

    def recoverable_jobs(self) -> list[Job]:
        states = tuple(state.value for state in RECOVERABLE_STATES)
        placeholders = ",".join("?" for _ in states)
        rows = self.connection.execute(
            f"""
            SELECT job_id, project_name, source_path_ids_json, replica_path_ids_json,
                   state, operator_origin, current_step, stats_json, policy_json,
                   recovery_cursor_json
            FROM jobs
            WHERE state IN ({placeholders})
            ORDER BY created_at ASC
            """,
            states,
        ).fetchall()
        return [_job_from_row(row) for row in rows]


class EventRepository:
    """Append-only event repository."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def append(
        self,
        event_type: str,
        *,
        job_id: str | None = None,
        reason: str | None = None,
        state_before: str | None = None,
        state_after: str | None = None,
        command: str | None = None,
        accepted: bool | None = None,
        payload: dict[str, object] | None = None,
    ) -> JobEvent:
        event = JobEvent(
            event_id=f"evt-{uuid4().hex[:12]}",
            event_type=event_type,
            job_id=job_id,
            reason=reason,
            state_before=state_before,
            state_after=state_after,
            command=command,
            accepted=accepted,
        )
        self.connection.execute(
            """
            INSERT INTO job_events (
              event_id, job_id, event_type, state_before, state_after, command,
              accepted, reason, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.job_id,
                event.event_type,
                event.state_before,
                event.state_after,
                event.command,
                None if event.accepted is None else int(event.accepted),
                event.reason,
                json.dumps(payload or {}),
            ),
        )
        return event

    def list_for_job(self, job_id: str) -> list[JobEvent]:
        rows = self.connection.execute(
            """
            SELECT event_id, job_id, event_type, state_before, state_after,
                   command, accepted, reason
            FROM job_events
            WHERE job_id = ?
            ORDER BY created_at ASC
            """,
            (job_id,),
        ).fetchall()
        return [
            JobEvent(
                event_id=str(row["event_id"]),
                event_type=str(row["event_type"]),
                job_id=str(row["job_id"]) if row["job_id"] is not None else None,
                reason=str(row["reason"]) if row["reason"] is not None else None,
                state_before=str(row["state_before"]) if row["state_before"] is not None else None,
                state_after=str(row["state_after"]) if row["state_after"] is not None else None,
                command=str(row["command"]) if row["command"] is not None else None,
                accepted=bool(row["accepted"]) if row["accepted"] is not None else None,
            )
            for row in rows
        ]


class VolumeRepository:
    """Persistence operations for runtime-discovered volumes."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_many(self, volumes: list[SystemVolume]) -> None:
        self.connection.executemany(
            """
            INSERT INTO system_volumes (
              volume_id, label, kind, display_path, status, bytes_available
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(volume_id) DO UPDATE SET
              label = excluded.label,
              kind = excluded.kind,
              display_path = excluded.display_path,
              status = excluded.status,
              bytes_available = excluded.bytes_available,
              last_seen_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    volume.volume_id,
                    volume.label,
                    volume.kind,
                    volume.display_path,
                    volume.status,
                    volume.bytes_available,
                )
                for volume in volumes
            ],
        )

    def list_all(self) -> list[SystemVolume]:
        rows = self.connection.execute(
            """
            SELECT volume_id, label, kind, display_path, status, bytes_available
            FROM system_volumes
            ORDER BY kind, label
            """
        ).fetchall()
        return [
            SystemVolume(
                volume_id=str(row["volume_id"]),
                label=str(row["label"]),
                kind=str(row["kind"]),
                display_path=str(row["display_path"]),
                status=str(row["status"]),
                bytes_available=row["bytes_available"],
            )
            for row in rows
        ]


class JobFileRepository:
    """Persistence operations for file-level replication results."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_result(self, result: JobFile) -> JobFile:
        self.connection.execute(
            """
            INSERT INTO job_files (
              file_id, job_id, source_path_id, source_relpath, size_bytes,
              checksum_source, status, error_code, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
              source_path_id = excluded.source_path_id,
              source_relpath = excluded.source_relpath,
              size_bytes = excluded.size_bytes,
              checksum_source = excluded.checksum_source,
              status = excluded.status,
              error_code = excluded.error_code,
              error_message = excluded.error_message,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                result.file_id,
                result.job_id,
                result.source_path_id,
                result.source_relpath,
                result.size_bytes,
                result.checksum_source,
                result.status,
                result.error_code,
                result.error_message,
            ),
        )
        self.connection.executemany(
            """
            INSERT INTO job_file_replicas (
              file_id, path_id, dest_relpath, checksum, status, error_code, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id, path_id) DO UPDATE SET
              dest_relpath = excluded.dest_relpath,
              checksum = excluded.checksum,
              status = excluded.status,
              error_code = excluded.error_code,
              error_message = excluded.error_message,
              updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    replica.file_id,
                    replica.path_id,
                    replica.dest_relpath,
                    replica.checksum,
                    replica.status,
                    replica.error_code,
                    replica.error_message,
                )
                for replica in result.replica_results
            ],
        )
        return result

    def list_for_job(self, job_id: str) -> list[JobFile]:
        rows = self.connection.execute(
            """
            SELECT file_id, job_id, source_path_id, source_relpath, size_bytes,
                   checksum_source, status, error_code, error_message
            FROM job_files
            WHERE job_id = ?
            ORDER BY source_path_id ASC, source_relpath ASC
            """,
            (job_id,),
        ).fetchall()
        files = [_job_file_from_row(row) for row in rows]
        if not files:
            return []
        replica_rows = self.connection.execute(
            f"""
            SELECT file_id, path_id, dest_relpath, checksum, status, error_code, error_message
            FROM job_file_replicas
            WHERE file_id IN ({",".join("?" for _ in files)})
            ORDER BY path_id ASC
            """,
            [file.file_id for file in files],
        ).fetchall()
        replicas_by_file: dict[str, list[JobFileReplica]] = {file.file_id: [] for file in files}
        for row in replica_rows:
            replicas_by_file[str(row["file_id"])].append(_replica_from_row(row))
        return [
            JobFile(
                **{
                    **file.__dict__,
                    "replica_results": tuple(replicas_by_file[file.file_id]),
                }
            )
            for file in files
        ]


class ClipRepository:
    """Persistence operations for parsed clip metadata."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert(self, clip: Clip) -> Clip:
        self.connection.execute(
            """
            INSERT INTO clips (
              clip_id, job_id, file_id, format_name, parser_version,
              metadata_json, integrity_status, capture_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(clip_id) DO UPDATE SET
              metadata_json = excluded.metadata_json,
              integrity_status = excluded.integrity_status,
              capture_status = excluded.capture_status
            """,
            (
                clip.clip_id,
                clip.job_id,
                clip.file_id,
                clip.format_name,
                clip.parser_version,
                clip.metadata_json,
                clip.integrity_status,
                clip.capture_status,
            ),
        )
        return clip

    def list_for_job(self, job_id: str) -> list[Clip]:
        rows = self.connection.execute(
            """
            SELECT clip_id, job_id, file_id, format_name, parser_version,
                   metadata_json, integrity_status, capture_status
            FROM clips
            WHERE job_id = ?
            ORDER BY clip_id ASC
            """,
            (job_id,),
        ).fetchall()
        return [_clip_from_row(row) for row in rows]


class ReportRepository:
    """Persistence operations for generated report artifacts."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert(self, report: Report) -> Report:
        self.connection.execute(
            """
            INSERT INTO reports (
              report_id, job_id, report_type, artifact_relpath, status, checksum, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, report_type) DO UPDATE SET
              artifact_relpath = excluded.artifact_relpath,
              status = excluded.status,
              checksum = excluded.checksum,
              error_message = excluded.error_message
            """,
            (
                report.report_id,
                report.job_id,
                report.report_type,
                report.artifact_relpath,
                report.status,
                report.checksum,
                report.error_message,
            ),
        )
        return report

    def list_for_job(self, job_id: str) -> list[Report]:
        rows = self.connection.execute(
            """
            SELECT report_id, job_id, report_type, artifact_relpath, status, checksum, error_message
            FROM reports
            WHERE job_id = ?
            ORDER BY report_type ASC
            """,
            (job_id,),
        ).fetchall()
        return [_report_from_row(row) for row in rows]


class SettingsRepository:
    """Key/value settings repository."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def set_json(self, key: str, value: dict[str, object]) -> SettingRecord:
        record = SettingRecord(key=key, value_json=json.dumps(value))
        self.connection.execute(
            """
            INSERT INTO settings (key, value_json)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value_json = excluded.value_json,
              updated_at = CURRENT_TIMESTAMP
            """,
            (record.key, record.value_json),
        )
        return record

    def get(self, key: str) -> SettingRecord | None:
        row = self.connection.execute(
            "SELECT key, value_json FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return SettingRecord(key=str(row["key"]), value_json=str(row["value_json"]))


def _job_from_row(row: sqlite3.Row) -> Job:
    return Job(
        job_id=str(row["job_id"]),
        project_name=str(row["project_name"]),
        source_path_ids=tuple(json.loads(str(row["source_path_ids_json"]))),
        replica_path_ids=tuple(json.loads(str(row["replica_path_ids_json"]))),
        state=str(row["state"]),
        operator_origin=str(row["operator_origin"]),
        current_step=str(row["current_step"]) if row["current_step"] is not None else None,
        stats_json=str(row["stats_json"]),
        policy_json=str(row["policy_json"]),
        recovery_cursor_json=(
            str(row["recovery_cursor_json"]) if row["recovery_cursor_json"] is not None else None
        ),
    )


def _job_file_from_row(row: sqlite3.Row) -> JobFile:
    return JobFile(
        file_id=str(row["file_id"]),
        job_id=str(row["job_id"]),
        source_path_id=str(row["source_path_id"]),
        source_relpath=str(row["source_relpath"]),
        size_bytes=int(row["size_bytes"]),
        checksum_source=str(row["checksum_source"]) if row["checksum_source"] is not None else None,
        status=str(row["status"]),
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        error_message=str(row["error_message"]) if row["error_message"] is not None else None,
    )


def _replica_from_row(row: sqlite3.Row) -> JobFileReplica:
    return JobFileReplica(
        file_id=str(row["file_id"]),
        path_id=str(row["path_id"]),
        dest_relpath=str(row["dest_relpath"]) if row["dest_relpath"] is not None else None,
        checksum=str(row["checksum"]) if row["checksum"] is not None else None,
        status=str(row["status"]),
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        error_message=str(row["error_message"]) if row["error_message"] is not None else None,
    )


def _clip_from_row(row: sqlite3.Row) -> Clip:
    return Clip(
        clip_id=str(row["clip_id"]),
        job_id=str(row["job_id"]),
        file_id=str(row["file_id"]),
        format_name=str(row["format_name"]),
        parser_version=str(row["parser_version"]),
        metadata_json=str(row["metadata_json"]),
        integrity_status=str(row["integrity_status"]),
        capture_status=str(row["capture_status"]),
    )


def _report_from_row(row: sqlite3.Row) -> Report:
    return Report(
        report_id=str(row["report_id"]),
        job_id=str(row["job_id"]),
        report_type=str(row["report_type"]),
        artifact_relpath=str(row["artifact_relpath"]),
        status=str(row["status"]),
        checksum=str(row["checksum"]) if row["checksum"] is not None else None,
        error_message=str(row["error_message"]) if row["error_message"] is not None else None,
    )


def deterministic_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{uuid5(NAMESPACE_URL, ':'.join(parts)).hex[:12]}"
