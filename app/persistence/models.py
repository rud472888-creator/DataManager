"""Dataclasses for the SQLite foundation models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    job_id: str
    project_name: str
    source_path_ids: tuple[str, ...]
    replica_path_ids: tuple[str, ...]
    state: str
    operator_origin: str
    current_step: str | None = None
    stats_json: str = "{}"
    policy_json: str = "{}"
    recovery_cursor_json: str | None = None


@dataclass(frozen=True)
class JobEvent:
    event_id: str
    event_type: str
    job_id: str | None
    reason: str | None
    state_before: str | None = None
    state_after: str | None = None
    command: str | None = None
    accepted: bool | None = None


@dataclass(frozen=True)
class JobFile:
    file_id: str
    job_id: str
    source_path_id: str
    source_relpath: str
    size_bytes: int
    status: str
    checksum_source: str | None = None
    replica_results: tuple[JobFileReplica, ...] = ()
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class JobFileReplica:
    file_id: str
    path_id: str
    dest_relpath: str | None
    checksum: str | None
    status: str
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class Clip:
    clip_id: str
    job_id: str
    file_id: str
    format_name: str
    parser_version: str
    metadata_json: str
    integrity_status: str
    capture_status: str


@dataclass(frozen=True)
class Report:
    report_id: str
    job_id: str
    report_type: str
    artifact_relpath: str
    status: str
    checksum: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class SystemVolume:
    volume_id: str
    label: str
    kind: str
    display_path: str
    status: str
    bytes_available: int | None = None


@dataclass(frozen=True)
class SettingRecord:
    key: str
    value_json: str
