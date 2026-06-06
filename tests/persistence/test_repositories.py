from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import EventRepository, JobRepository
from app.runtime.state_machine import JobState


def test_job_repository_lists_active_and_recoverable_jobs(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    with database.session() as connection:
        apply_migrations(connection)
        jobs = JobRepository(connection)
        active = jobs.create_job(
            project_name="Active",
            source_path_ids=("source-a", "source-b"),
            replica_path_ids=("path1", "path2", "path3"),
            operator_origin="test",
        )
        failed = jobs.create_job(
            project_name="Failed",
            source_path_ids=("source-a",),
            replica_path_ids=("path1", "path2"),
            operator_origin="test",
        )
        jobs.update_state(failed.job_id, JobState.FAILED)

    with database.session() as connection:
        jobs = JobRepository(connection)
        active_job_id = jobs.active_job_id()
        recoverable = jobs.recoverable_jobs()

    assert active_job_id == active.job_id
    assert [job.job_id for job in recoverable] == [active.job_id, failed.job_id]


def test_event_repository_is_append_only_ordered(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job()
        events = EventRepository(connection)
        first = events.append("first", job_id=job.job_id)
        second = events.append("second", job_id=job.job_id)

    with database.session() as connection:
        rows = EventRepository(connection).list_for_job(job.job_id)

    assert [event.event_id for event in rows] == [first.event_id, second.event_id]
