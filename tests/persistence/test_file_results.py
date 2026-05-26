from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.models import JobFile
from app.persistence.repositories import JobFileRepository, JobRepository


def test_job_file_repository_persists_file_level_outcomes(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job()
        result = JobFile(
            file_id="file-1",
            job_id=job.job_id,
            source_relpath="A001/A001_C001.braw",
            size_bytes=10,
            status="verified",
            dest_main_relpath="main/Project/01_Footage/R#1/A001/A001_C001.braw",
            dest_backup_relpath="backup/Project/01_Footage/R#1/A001/A001_C001.braw",
            checksum_source="abc",
            checksum_main="abc",
            checksum_backup="abc",
        )
        JobFileRepository(connection).upsert_result(result)

    with database.session() as connection:
        files = JobFileRepository(connection).list_for_job(job.job_id)

    assert len(files) == 1
    assert files[0].status == "verified"
    assert files[0].checksum_source == files[0].checksum_main == files[0].checksum_backup
