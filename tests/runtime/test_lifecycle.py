import pytest

from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import EventRepository, JobRepository
from app.runtime.lifecycle import JobCreateRequest, JobLifecycleService, LifecycleError
from app.runtime.recovery import RecoveryLoader
from app.runtime.state_machine import CommandName, JobState


@pytest.fixture()
def lifecycle(tmp_path) -> JobLifecycleService:
    database = Database(tmp_path / "fdm.sqlite3")
    with database.session() as connection:
        apply_migrations(connection)
    return JobLifecycleService(database)


def _request(project_name: str = "Runtime Test") -> JobCreateRequest:
    return JobCreateRequest(
        project_name=project_name,
        source_path_ids=("mock-source",),
        replica_path_ids=("path1", "path2"),
        operator_origin="runtime_test",
        policy={},
    )


def test_job_creation_records_event_and_blocks_second_active_job(
    lifecycle: JobLifecycleService,
) -> None:
    job = lifecycle.create_job(_request())

    assert job.state == "QUEUED"
    with pytest.raises(LifecycleError, match="single active job"):
        lifecycle.create_job(_request("Blocked"))

    with lifecycle.database.session() as connection:
        events = EventRepository(connection).list_for_job(job.job_id)

    assert [event.event_type for event in events] == ["job_created"]


def test_transition_records_accepted_and_rejected_events(lifecycle: JobLifecycleService) -> None:
    job = lifecycle.create_job(_request())

    accepted = lifecycle.transition_job(job.job_id, JobState.SCANNING)
    rejected = lifecycle.transition_job(job.job_id, JobState.COMPLETED)

    assert accepted.accepted is True
    assert rejected.accepted is False

    with lifecycle.database.session() as connection:
        updated = JobRepository(connection).get(job.job_id)
        events = EventRepository(connection).list_for_job(job.job_id)

    assert updated is not None
    assert updated.state == "SCANNING"
    assert events[-1].accepted is False
    assert events[-1].state_before == "SCANNING"


def test_command_decision_updates_state_when_accepted(lifecycle: JobLifecycleService) -> None:
    job = lifecycle.create_job(_request())

    decision = lifecycle.request_command(job.job_id, CommandName.CANCEL)

    assert decision.accepted is True
    assert decision.state_after is JobState.CANCELLED
    with lifecycle.database.session() as connection:
        updated = JobRepository(connection).get(job.job_id)
        events = EventRepository(connection).list_for_job(job.job_id)

    assert updated is not None
    assert updated.state == "CANCELLED"
    assert events[-1].command == "cancel"
    assert events[-1].accepted is True


def test_recovery_loader_returns_only_recoverable_jobs(lifecycle: JobLifecycleService) -> None:
    queued = lifecycle.create_job(_request("Queued"))
    lifecycle.request_command(queued.job_id, CommandName.CANCEL)
    failed = lifecycle.create_job(_request("Failed"))
    lifecycle.transition_job(failed.job_id, JobState.SCANNING)
    lifecycle.transition_job(failed.job_id, JobState.FAILED)

    plan = RecoveryLoader(lifecycle).load()

    assert [job.state for job in plan.jobs] == ["FAILED"]
    assert "recovery candidates" in plan.reason
