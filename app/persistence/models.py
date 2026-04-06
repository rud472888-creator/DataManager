from __future__ import annotations

import json
from dataclasses import dataclass
from sqlite3 import Row
from typing import Any


@dataclass(slots=True)
class JobRecord:
    job_id: str
    retry_of_job_id: str | None
    project_name: str
    source_volume_id: str
    dest_main_id: str
    dest_backup_id: str | None
    state: str
    current_step: str
    resume_step: str | None
    operator_origin: str
    policy_json: str
    stats_json: str
    warning_count: int
    error_count: int
    current_file_relpath: str | None
    created_at: str
    started_at: str | None
    ended_at: str | None
    last_event_id: int

    @classmethod
    def from_row(cls, row: Row) -> "JobRecord":
        return cls(**dict(row))

    def policy(self) -> dict[str, Any]:
        return json.loads(self.policy_json)

    def stats(self) -> dict[str, Any]:
        return json.loads(self.stats_json)


@dataclass(slots=True)
class EventRecord:
    event_id: int
    job_id: str | None
    event_type: str
    level: str
    from_state: str | None
    to_state: str | None
    command_name: str | None
    command_status: str | None
    origin: str
    reason_code: str | None
    message: str
    payload_json: str
    created_at: str

    @classmethod
    def from_row(cls, row: Row) -> "EventRecord":
        return cls(**dict(row))

    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)


@dataclass(slots=True)
class VolumeRecord:
    volume_id: str
    display_name: str
    mount_path: str
    volume_role: str
    is_removable: int
    filesystem_type: str | None
    capacity_bytes: int | None
    free_bytes: int | None
    serial_hint: str | None
    approval_state: str
    last_seen_at: str
    metadata_json: str

    @classmethod
    def from_row(cls, row: Row) -> "VolumeRecord":
        return cls(**dict(row))

    def metadata(self) -> dict[str, Any]:
        return json.loads(self.metadata_json)


@dataclass(slots=True)
class JobFileRecord:
    job_file_id: int
    job_id: str
    relative_path: str
    size_bytes: int
    parser_name: str | None
    source_checksum_sha256: str | None
    main_checksum_sha256: str | None
    backup_checksum_sha256: str | None
    copy_main_state: str
    copy_backup_state: str
    verify_main_state: str
    verify_backup_state: str
    parse_state: str
    capture_state: str
    warning_code: str | None
    error_code: str | None
    metadata_json: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Row) -> "JobFileRecord":
        return cls(**dict(row))

    def metadata(self) -> dict[str, Any]:
        return json.loads(self.metadata_json) if self.metadata_json else {}
