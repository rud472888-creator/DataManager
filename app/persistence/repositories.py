from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.persistence.db import Database
from app.persistence.models import EventRecord, JobFileRecord, JobRecord, VolumeRecord
from app.runtime.events import utc_now_iso
from app.runtime.state_machine import JobCommand, JobState, validate_transition


class EventsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def append_event(
        self,
        *,
        job_id: str | None,
        event_type: str,
        level: str,
        origin: str,
        message: str,
        payload: dict[str, Any] | None = None,
        from_state: str | None = None,
        to_state: str | None = None,
        command_name: str | None = None,
        command_status: str | None = None,
        reason_code: str | None = None,
    ) -> int:
        created_at = utc_now_iso()
        payload_json = json.dumps(payload or {}, sort_keys=True)
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO job_events (
                    job_id, event_type, level, from_state, to_state, command_name,
                    command_status, origin, reason_code, message, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    event_type,
                    level,
                    from_state,
                    to_state,
                    command_name,
                    command_status,
                    origin,
                    reason_code,
                    message,
                    payload_json,
                    created_at,
                ),
            )
            event_id = int(cursor.lastrowid)
            if job_id is not None:
                connection.execute(
                    "UPDATE jobs SET last_event_id = ? WHERE job_id = ?",
                    (event_id, job_id),
                )
            connection.commit()
            return event_id

    def list_events_for_job(self, job_id: str) -> list[EventRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY event_id ASC",
                (job_id,),
            ).fetchall()
        return [EventRecord.from_row(row) for row in rows]


class JobsRepository:
    def __init__(self, database: Database, events_repository: EventsRepository) -> None:
        self.database = database
        self.events_repository = events_repository

    def create_job(self, record: dict[str, Any]) -> JobRecord:
        created_at = utc_now_iso()
        payload = {
            "job_id": record["job_id"],
            "project_name": record["project_name"],
            "source_volume_id": record["source_volume_id"],
            "dest_main_id": record["dest_main_id"],
            "dest_backup_id": record.get("dest_backup_id"),
            "state": record["state"],
        }
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, retry_of_job_id, project_name, source_volume_id, dest_main_id,
                    dest_backup_id, state, current_step, resume_step, operator_origin,
                    policy_json, stats_json, warning_count, error_count, current_file_relpath,
                    created_at, started_at, ended_at, last_event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["job_id"],
                    record.get("retry_of_job_id"),
                    record["project_name"],
                    record["source_volume_id"],
                    record["dest_main_id"],
                    record.get("dest_backup_id"),
                    record["state"],
                    record["current_step"],
                    record.get("resume_step"),
                    record["operator_origin"],
                    json.dumps(record["policy_json"], sort_keys=True),
                    json.dumps(record["stats_json"], sort_keys=True),
                    record.get("warning_count", 0),
                    record.get("error_count", 0),
                    record.get("current_file_relpath"),
                    created_at,
                    record.get("started_at"),
                    record.get("ended_at"),
                    0,
                ),
            )
            connection.commit()
        event_id = self.events_repository.append_event(
            job_id=record["job_id"],
            event_type="job.created",
            level="INFO",
            origin=record["operator_origin"],
            message="Job created in QUEUED state",
            payload=payload,
            to_state=record["state"],
        )
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE jobs SET last_event_id = ? WHERE job_id = ?",
                (event_id, record["job_id"]),
            )
            connection.commit()
        created = self.get_job(record["job_id"])
        assert created is not None
        return created

    def get_job(self, job_id: str) -> JobRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return JobRecord.from_row(row) if row else None

    def list_jobs(self, state: str | None = None) -> list[JobRecord]:
        with self.database.connect() as connection:
            if state is None:
                rows = connection.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC, job_id DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC, job_id DESC",
                    (state,),
                ).fetchall()
        return [JobRecord.from_row(row) for row in rows]

    def list_active_jobs(self) -> list[JobRecord]:
        active_states = tuple(
            state.value
            for state in (
                JobState.SCANNING,
                JobState.PREPARING,
                JobState.COPYING,
                JobState.PAUSING,
                JobState.VERIFYING,
                JobState.PARSING,
                JobState.CAPTURING,
                JobState.REPORTING,
            )
        )
        placeholders = ", ".join("?" for _ in active_states)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM jobs WHERE state IN ({placeholders}) ORDER BY created_at ASC",
                active_states,
            ).fetchall()
        return [JobRecord.from_row(row) for row in rows]

    def get_next_queued_job(self) -> JobRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE state = ? ORDER BY created_at ASC, job_id ASC LIMIT 1",
                (JobState.QUEUED.value,),
            ).fetchone()
        return JobRecord.from_row(row) if row else None

    def transition_job_state(
        self,
        *,
        job_id: str,
        new_state: JobState,
        current_step: str,
        message: str,
        origin: str,
        reason_code: str | None = None,
    ) -> JobRecord:
        current = self.get_job(job_id)
        if current is None:
            raise KeyError(job_id)
        current_state = JobState(current.state)
        allowed, reason = validate_transition(current_state, new_state)
        if not allowed:
            raise ValueError(reason)
        ended_at = utc_now_iso() if new_state in (JobState.WARN, JobState.FAILED, JobState.CANCELLED, JobState.COMPLETED) else None
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET state = ?, current_step = ?, ended_at = COALESCE(?, ended_at)
                WHERE job_id = ?
                """,
                (new_state.value, current_step, ended_at, job_id),
            )
            connection.commit()
        event_id = self.events_repository.append_event(
            job_id=job_id,
            event_type="job.state_changed",
            level="INFO",
            origin=origin,
            message=message,
            from_state=current_state.value,
            to_state=new_state.value,
            reason_code=reason_code,
            payload={"current_step": current_step},
        )
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE jobs SET last_event_id = ? WHERE job_id = ?",
                (event_id, job_id),
            )
            connection.commit()
        updated = self.get_job(job_id)
        assert updated is not None
        return updated

    def update_job_runtime_fields(
        self,
        *,
        job_id: str,
        stats: dict[str, Any] | None = None,
        current_step: str | None = None,
        current_file_relpath: str | None = None,
        warning_count: int | None = None,
        error_count: int | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> None:
        updates: list[str] = []
        values: list[Any] = []
        if stats is not None:
            updates.append("stats_json = ?")
            values.append(json.dumps(stats, sort_keys=True))
        if current_step is not None:
            updates.append("current_step = ?")
            values.append(current_step)
        if current_file_relpath is not None:
            updates.append("current_file_relpath = ?")
            values.append(current_file_relpath)
        if warning_count is not None:
            updates.append("warning_count = ?")
            values.append(warning_count)
        if error_count is not None:
            updates.append("error_count = ?")
            values.append(error_count)
        if started_at is not None:
            updates.append("started_at = ?")
            values.append(started_at)
        if ended_at is not None:
            updates.append("ended_at = ?")
            values.append(ended_at)
        if not updates:
            return
        values.append(job_id)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
                tuple(values),
            )
            connection.commit()

    def append_command_result(
        self,
        *,
        job_id: str,
        command: JobCommand,
        accepted: bool,
        message: str,
        origin: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        return self.events_repository.append_event(
            job_id=job_id,
            event_type="job.command_result",
            level="INFO" if accepted else "WARN",
            origin=origin,
            message=message,
            command_name=command.value,
            command_status="accepted" if accepted else "rejected",
            payload=payload or {},
        )

    def clone_job_for_retry(self, job_id: str, origin: str) -> JobRecord:
        existing = self.get_job(job_id)
        if existing is None:
            raise KeyError(job_id)
        new_job_id = f"JOB-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        clone_input = {
            "job_id": new_job_id,
            "retry_of_job_id": existing.job_id,
            "project_name": existing.project_name,
            "source_volume_id": existing.source_volume_id,
            "dest_main_id": existing.dest_main_id,
            "dest_backup_id": existing.dest_backup_id,
            "state": JobState.QUEUED.value,
            "current_step": "queued",
            "resume_step": None,
            "operator_origin": origin,
            "policy_json": existing.policy(),
            "stats_json": existing.stats(),
            "warning_count": 0,
            "error_count": 0,
            "current_file_relpath": None,
        }
        return self.create_job(clone_input)


class VolumesRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_volume(self, record: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO system_volumes (
                    volume_id, display_name, mount_path, volume_role, is_removable,
                    filesystem_type, capacity_bytes, free_bytes, serial_hint, approval_state,
                    last_seen_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(volume_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    mount_path = excluded.mount_path,
                    volume_role = excluded.volume_role,
                    is_removable = excluded.is_removable,
                    filesystem_type = excluded.filesystem_type,
                    capacity_bytes = excluded.capacity_bytes,
                    free_bytes = excluded.free_bytes,
                    serial_hint = excluded.serial_hint,
                    approval_state = excluded.approval_state,
                    last_seen_at = excluded.last_seen_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    record["volume_id"],
                    record["display_name"],
                    record["mount_path"],
                    record["volume_role"],
                    record["is_removable"],
                    record.get("filesystem_type"),
                    record.get("capacity_bytes"),
                    record.get("free_bytes"),
                    record.get("serial_hint"),
                    record["approval_state"],
                    record["last_seen_at"],
                    record["metadata_json"],
                ),
            )
            connection.commit()

    def list_volumes(self) -> list[VolumeRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM system_volumes ORDER BY volume_role ASC, display_name ASC"
            ).fetchall()
        return [VolumeRecord.from_row(row) for row in rows]

    def get_volume(self, volume_id: str) -> VolumeRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM system_volumes WHERE volume_id = ?",
                (volume_id,),
            ).fetchone()
        return VolumeRecord.from_row(row) if row else None


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_defaults(self, defaults: dict[str, Any]) -> None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            for key, value in defaults.items():
                connection.execute(
                    """
                    INSERT INTO settings (key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO NOTHING
                    """,
                    (key, json.dumps(value, sort_keys=True), now),
                )
            connection.commit()

    def get_json(self, key: str, default: Any = None) -> Any:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return json.loads(row["value_json"]) if row else default

    def set_json(self, key: str, value: Any) -> None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, sort_keys=True), now),
            )
            connection.commit()

    @staticmethod
    def hash_token(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()


class ReportsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_reports_for_job(self, job_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM reports WHERE job_id = ? ORDER BY created_at ASC",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class JobFilesRepository:
    def __init__(self, database: Database, events_repository: EventsRepository) -> None:
        self.database = database
        self.events_repository = events_repository

    def replace_for_job(self, job_id: str, files: list[dict[str, Any]]) -> list[JobFileRecord]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM job_files WHERE job_id = ?", (job_id,))
            connection.executemany(
                """
                INSERT INTO job_files (
                    job_id, relative_path, size_bytes, parser_name, source_checksum_sha256,
                    main_checksum_sha256, backup_checksum_sha256, copy_main_state,
                    copy_backup_state, verify_main_state, verify_backup_state,
                    parse_state, capture_state, warning_code, error_code, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        job_id,
                        file["relative_path"],
                        file["size_bytes"],
                        file.get("parser_name"),
                        None,
                        None,
                        None,
                        "PENDING",
                        "PENDING" if file.get("has_backup", True) else "SKIPPED",
                        "PENDING",
                        "PENDING" if file.get("has_backup", True) else "SKIPPED",
                        "PENDING",
                        "PENDING",
                        None,
                        None,
                        json.dumps(file.get("metadata", {}), sort_keys=True),
                        now,
                        now,
                    )
                    for file in files
                ],
            )
            connection.commit()
        self.events_repository.append_event(
            job_id=job_id,
            event_type="job.scan_manifest_created",
            level="INFO",
            origin="runtime.scan",
            message=f"Scanned {len(files)} files into job_files",
            payload={"files": len(files)},
        )
        return self.list_for_job(job_id)

    def list_for_job(self, job_id: str) -> list[JobFileRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM job_files WHERE job_id = ? ORDER BY relative_path ASC",
                (job_id,),
            ).fetchall()
        return [JobFileRecord.from_row(row) for row in rows]

    def list_copy_pending(self, job_id: str) -> list[JobFileRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM job_files
                WHERE job_id = ?
                  AND (
                    copy_main_state != 'COPIED'
                    OR copy_backup_state NOT IN ('COPIED', 'SKIPPED')
                  )
                ORDER BY relative_path ASC
                """,
                (job_id,),
            ).fetchall()
        return [JobFileRecord.from_row(row) for row in rows]

    def update_copy_state(
        self,
        *,
        job_file_id: int,
        main_state: str | None = None,
        backup_state: str | None = None,
        warning_code: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        updates = ["updated_at = ?"]
        values: list[Any] = [utc_now_iso()]
        if main_state is not None:
            updates.append("copy_main_state = ?")
            values.append(main_state)
        if backup_state is not None:
            updates.append("copy_backup_state = ?")
            values.append(backup_state)
        if warning_code is not None:
            updates.append("warning_code = ?")
            values.append(warning_code)
        if error_code is not None:
            updates.append("error_code = ?")
            values.append(error_code)
        if metadata is not None:
            updates.append("metadata_json = ?")
            values.append(json.dumps(metadata, sort_keys=True))
        values.append(job_file_id)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE job_files SET {', '.join(updates)} WHERE job_file_id = ?",
                tuple(values),
            )
            connection.commit()

    def update_verify_state(
        self,
        *,
        job_file_id: int,
        source_checksum_sha256: str | None = None,
        main_checksum_sha256: str | None = None,
        backup_checksum_sha256: str | None = None,
        verify_main_state: str | None = None,
        verify_backup_state: str | None = None,
        warning_code: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        updates = ["updated_at = ?"]
        values: list[Any] = [utc_now_iso()]
        if source_checksum_sha256 is not None:
            updates.append("source_checksum_sha256 = ?")
            values.append(source_checksum_sha256)
        if main_checksum_sha256 is not None:
            updates.append("main_checksum_sha256 = ?")
            values.append(main_checksum_sha256)
        if backup_checksum_sha256 is not None:
            updates.append("backup_checksum_sha256 = ?")
            values.append(backup_checksum_sha256)
        if verify_main_state is not None:
            updates.append("verify_main_state = ?")
            values.append(verify_main_state)
        if verify_backup_state is not None:
            updates.append("verify_backup_state = ?")
            values.append(verify_backup_state)
        if warning_code is not None:
            updates.append("warning_code = ?")
            values.append(warning_code)
        if error_code is not None:
            updates.append("error_code = ?")
            values.append(error_code)
        if metadata is not None:
            updates.append("metadata_json = ?")
            values.append(json.dumps(metadata, sort_keys=True))
        values.append(job_file_id)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE job_files SET {', '.join(updates)} WHERE job_file_id = ?",
                tuple(values),
            )
            connection.commit()

    def list_in_progress(self, job_id: str) -> list[JobFileRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM job_files
                WHERE job_id = ?
                  AND (
                    copy_main_state = 'IN_PROGRESS'
                    OR copy_backup_state = 'IN_PROGRESS'
                    OR verify_main_state = 'IN_PROGRESS'
                    OR verify_backup_state = 'IN_PROGRESS'
                  )
                ORDER BY relative_path ASC
                """,
                (job_id,),
            ).fetchall()
        return [JobFileRecord.from_row(row) for row in rows]

    def list_verify_pending(self, job_id: str) -> list[JobFileRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM job_files
                WHERE job_id = ?
                  AND copy_main_state = 'COPIED'
                  AND (
                    verify_main_state != 'VERIFIED'
                    OR verify_backup_state NOT IN ('VERIFIED', 'SKIPPED')
                  )
                ORDER BY relative_path ASC
                """,
                (job_id,),
            ).fetchall()
        return [JobFileRecord.from_row(row) for row in rows]

    def mark_in_progress_as_failed(self, job_id: str, error_code: str) -> int:
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE job_files
                SET
                    copy_main_state = CASE WHEN copy_main_state = 'IN_PROGRESS' THEN 'FAILED' ELSE copy_main_state END,
                    copy_backup_state = CASE WHEN copy_backup_state = 'IN_PROGRESS' THEN 'FAILED' ELSE copy_backup_state END,
                    verify_main_state = CASE WHEN verify_main_state = 'IN_PROGRESS' THEN 'FAILED' ELSE verify_main_state END,
                    verify_backup_state = CASE WHEN verify_backup_state = 'IN_PROGRESS' THEN 'FAILED' ELSE verify_backup_state END,
                    error_code = CASE
                        WHEN copy_main_state = 'IN_PROGRESS'
                          OR copy_backup_state = 'IN_PROGRESS'
                          OR verify_main_state = 'IN_PROGRESS'
                          OR verify_backup_state = 'IN_PROGRESS'
                        THEN ?
                        ELSE error_code
                    END,
                    updated_at = ?
                WHERE job_id = ?
                  AND (
                    copy_main_state = 'IN_PROGRESS'
                    OR copy_backup_state = 'IN_PROGRESS'
                    OR verify_main_state = 'IN_PROGRESS'
                    OR verify_backup_state = 'IN_PROGRESS'
                  )
                """,
                (error_code, now, job_id),
            )
            connection.commit()
            return cursor.rowcount


class PersistenceBundle:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.events = EventsRepository(database)
        self.jobs = JobsRepository(database, self.events)
        self.job_files = JobFilesRepository(database, self.events)
        self.volumes = VolumesRepository(database)
        self.settings = SettingsRepository(database)
        self.reports = ReportsRepository(database)

    def as_dict(self) -> dict[str, object]:
        return {
            "database": self.database,
            "events": self.events,
            "jobs": self.jobs,
            "job_files": self.job_files,
            "volumes": self.volumes,
            "settings": self.settings,
            "reports": self.reports,
        }
