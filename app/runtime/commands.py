from __future__ import annotations

from dataclasses import dataclass

from app.runtime.state_machine import JobCommand


@dataclass(slots=True)
class CommandRequest:
    job_id: str
    command: JobCommand
    origin: str


@dataclass(slots=True)
class CommandResult:
    job_id: str
    command: str
    accepted: bool
    message: str
    persisted_event_id: int
