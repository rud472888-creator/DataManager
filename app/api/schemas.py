from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    project_name: str = Field(min_length=1)
    source_volume_id: str
    dest_main_id: str
    dest_backup_id: str | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    operator_origin: str = "remote_web"


class JobCommandRequest(BaseModel):
    command: Literal["pause", "resume", "cancel", "retry"]
    operator_origin: str = "remote_web"


class RuntimeStatusResponse(BaseModel):
    app_name: str
    app_version: str
    status: str
    started_at: str
    db_path: str
    active_job_id: str | None
    queue_depth: int
    dependencies: dict[str, Any]
    stubbed_components: list[str]
