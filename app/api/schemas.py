"""Typed response payloads for the foundation API."""

from __future__ import annotations

from typing import Literal, TypedDict

CapabilityState = Literal["available", "unavailable", "partial", "unknown"]
RuntimeState = Literal["online", "degraded", "offline"]
VolumeKind = Literal["source", "destination"]
VolumeStatus = Literal["available", "missing", "busy", "read-only", "low-space"]


class CapabilityPayload(TypedDict):
    checksum: CapabilityState
    supported_offload_formats: list[str]
    supported_offload_suffixes: list[str]


class RuntimeStatusPayload(TypedDict):
    runtime: RuntimeState
    version: str
    platform: str
    active_job_id: str | None
    capabilities: CapabilityPayload
    messages: list[str]


class WebSocketStatusPayload(RuntimeStatusPayload):
    type: Literal["runtime_status"]
    event_id: str
    timestamp: str


class VolumePayload(TypedDict):
    volume_id: str
    label: str
    kind: VolumeKind
    status: VolumeStatus
    display_path: str
    bytes_available: int | None


class VolumeListPayload(TypedDict):
    sources: list[VolumePayload]
    destinations: list[VolumePayload]


class CommandRequestPayload(TypedDict):
    command: str
    operator_origin: str
    request_id: str


class CommandDecisionPayload(TypedDict):
    job_id: str
    command: str
    accepted: bool
    state_before: str
    state_after: str
    reason: str


class JobCreatePayload(TypedDict):
    project_name: str
    source_volume_id: str
    dest_main_id: str
    dest_backup_id: str | None
    operator_origin: str
    policy: dict[str, object]


class JobSummaryPayload(TypedDict):
    job_id: str
    project_name: str
    source_volume_id: str
    dest_main_id: str
    dest_backup_id: str | None
    state: str
    current_step: str | None


class JobListPayload(TypedDict):
    jobs: list[JobSummaryPayload]


class SettingsPayload(TypedDict):
    token_required: bool
    allowed_destinations: list[str]
    data_dir: str


class ErrorDetailPayload(TypedDict):
    code: str
    message: str
    details: dict[str, object]


class ErrorPayload(TypedDict):
    error: ErrorDetailPayload
