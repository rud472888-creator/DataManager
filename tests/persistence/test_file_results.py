from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.models import JobFile, JobFileReplica
from app.persistence.repositories import JobFileRepository, JobRepository


def test_job_file_repository_persists_file_level_outcomes(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job()
        result = JobFile(
            file_id="file-1",
            job_id=job.job_id,
            source_path_id="path1",
            source_relpath="A001/A001_C001.braw",
            size_bytes=10,
            status="verified",
            checksum_source="abc",
            replica_results=(
                JobFileReplica(
                    file_id="file-1",
                    path_id="path1",
                    dest_relpath="01_Footage/R#1/path1/A001/A001_C001.braw",
                    checksum="abc",
                    status="verified",
                ),
                JobFileReplica(
                    file_id="file-1",
                    path_id="path2",
                    dest_relpath="01_Footage/R#1/path1/A001/A001_C001.braw",
                    checksum="abc",
                    status="verified",
                ),
            ),
        )
        JobFileRepository(connection).upsert_result(result)

    with database.session() as connection:
        files = JobFileRepository(connection).list_for_job(job.job_id)

    assert len(files) == 1
    assert files[0].status == "verified"
    assert files[0].checksum_source == "abc"
    assert {replica.path_id for replica in files[0].replica_results} == {"path1", "path2"}
    assert {replica.checksum for replica in files[0].replica_results} == {"abc"}
