"""Runtime-owned job lifecycle service."""

from __future__ import annotations

from dataclasses import dataclass

from app.persistence.db import Database
from app.persistence.models import Job
from app.persistence.repositories import EventRepository, JobRepository
from app.runtime.state_machine import (
    CommandDecision,
    CommandName,
    JobState,
    TransitionDecision,
    decide_command,
    decide_transition,
)


@dataclass(frozen=True)
class JobCreateRequest:
    project_name: str
    source_volume_id: str
    dest_main_id: str
    dest_backup_id: str | None
    operator_origin: str
    policy: dict[str, object] | None = None


class LifecycleError(RuntimeError):
    """Raised for rejected lifecycle operations."""


class JobLifecycleService:
    """Runtime owner for state transitions and event recording."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_job(self, request: JobCreateRequest) -> Job:
        with self.database.session() as connection:
            jobs = JobRepository(connection)
            active_job_id = jobs.active_job_id()
            if active_job_id is not None:
                raise LifecycleError(f"single active job policy blocks new job: {active_job_id}")
            job = jobs.create_job(
                project_name=request.project_name,
                source_volume_id=request.source_volume_id,
                dest_main_id=request.dest_main_id,
                dest_backup_id=request.dest_backup_id,
                operator_origin=request.operator_origin,
                policy=request.policy,
            )
            EventRepository(connection).append(
                "job_created",
                job_id=job.job_id,
                state_after=job.state,
                reason="job queued",
            )
            return job

    def list_jobs(self) -> list[Job]:
        with self.database.session() as connection:
            return JobRepository(connection).list_all()

    def transition_job(self, job_id: str, target: JobState) -> TransitionDecision:
        with self.database.session() as connection:
            jobs = JobRepository(connection)
            events = EventRepository(connection)
            job = jobs.get(job_id)
            if job is None:
                raise LifecycleError(f"job not found: {job_id}")
            decision = decide_transition(JobState(job.state), target)
            events.append(
                "state_transition",
                job_id=job.job_id,
                state_before=job.state,
                state_after=target.value,
                accepted=decision.accepted,
                reason=decision.reason,
            )
            if decision.accepted:
                jobs.update_state(job.job_id, target, current_step=target.value.lower())
            return decision

    def request_command(self, job_id: str, command: CommandName) -> CommandDecision:
        with self.database.session() as connection:
            jobs = JobRepository(connection)
            events = EventRepository(connection)
            job = jobs.get(job_id)
            if job is None:
                raise LifecycleError(f"job not found: {job_id}")
            decision = decide_command(JobState(job.state), command)
            events.append(
                "command_decision",
                job_id=job.job_id,
                state_before=job.state,
                state_after=decision.state_after.value,
                command=command.value,
                accepted=decision.accepted,
                reason=decision.reason,
            )
            if decision.accepted and decision.state_after != JobState(job.state):
                jobs.update_state(
                    job.job_id,
                    decision.state_after,
                    current_step=decision.state_after.value.lower(),
                )
            return decision

    def recoverable_jobs(self) -> list[Job]:
        with self.database.session() as connection:
            return JobRepository(connection).recoverable_jobs()
