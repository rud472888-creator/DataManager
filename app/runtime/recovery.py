"""Restart recovery scaffolding."""

from __future__ import annotations

from dataclasses import dataclass

from app.persistence.models import Job
from app.runtime.lifecycle import JobLifecycleService


@dataclass(frozen=True)
class RecoveryPlan:
    jobs: list[Job]
    reason: str


class RecoveryLoader:
    """Load jobs that are safe to inspect after restart."""

    def __init__(self, lifecycle: JobLifecycleService) -> None:
        self.lifecycle = lifecycle

    def load(self) -> RecoveryPlan:
        jobs = self.lifecycle.recoverable_jobs()
        return RecoveryPlan(
            jobs=jobs,
            reason="queued, paused, warn, and failed jobs are recovery candidates",
        )
