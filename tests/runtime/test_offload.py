from pathlib import Path

from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import JobFileRepository, JobRepository
from app.runtime.offload import DestinationPlan, OffloadService
from app.runtime.scan import scan_source
from app.runtime.state_machine import JobState


def _make_job(database: Database) -> str:
    with database.session() as connection:
        apply_migrations(connection)
        return JobRepository(connection).create_stub_job().job_id


def _write_source(root: Path) -> None:
    (root / "A001").mkdir(parents=True)
    (root / "A001" / "A001_C001.braw").write_bytes(b"clip-one")
    (root / "A001" / "A001_C002.braw").write_bytes(b"clip-two")
    (root / ".DS_Store").write_bytes(b"ignored")
    (root / "._A001_C003.braw").write_bytes(b"ignored")


def test_scan_source_filters_supported_files(tmp_path) -> None:
    source = tmp_path / "source"
    _write_source(source)

    files = scan_source(source)

    assert [file.relpath.as_posix() for file in files] == [
        "A001/A001_C001.braw",
        "A001/A001_C002.braw",
    ]


def test_offload_success_copies_main_backup_and_persists_results(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)

    result = OffloadService(database).execute(
        job_id=job_id,
        source_root=source,
        plan=DestinationPlan(
            project_name="Project",
            main_root=tmp_path / "main",
            backup_root=tmp_path / "backup",
        ),
    )

    assert result.state is JobState.COMPLETED
    assert (tmp_path / "main/Project/01_footage/A001/A001_C001.braw").exists()
    assert (tmp_path / "backup/Project/01_footage/A001/A001_C002.braw").exists()
    assert (tmp_path / "main/Project/00_master/reports").is_dir()

    with database.session() as connection:
        job = JobRepository(connection).get(job_id)
        files = JobFileRepository(connection).list_for_job(job_id)

    assert job is not None
    assert job.state == "COMPLETED"
    assert len(files) == 2
    assert {file.status for file in files} == {"verified"}
    assert all(file.checksum_source == file.checksum_main == file.checksum_backup for file in files)


def test_collision_blocks_blind_overwrite(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)
    collision = tmp_path / "main/Project/01_footage/A001/A001_C001.braw"
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"existing")

    result = OffloadService(database).execute(
        job_id=job_id,
        source_root=source,
        plan=DestinationPlan(
            project_name="Project",
            main_root=tmp_path / "main",
            backup_root=tmp_path / "backup",
        ),
    )

    assert result.state is JobState.FAILED
    assert "collision" in result.reason
    assert collision.read_bytes() == b"existing"


def test_backup_failure_yields_warn_after_main_success(tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)

    from app.runtime import offload

    original = offload._copy_and_hash

    def flaky_backup(source_path: Path, target: Path) -> str:
        if "backup" in target.parts:
            raise OSError("backup device unavailable")
        return original(source_path, target)

    monkeypatch.setattr(offload, "_copy_and_hash", flaky_backup)

    result = OffloadService(database).execute(
        job_id=job_id,
        source_root=source,
        plan=DestinationPlan(
            project_name="Project",
            main_root=tmp_path / "main",
            backup_root=tmp_path / "backup",
        ),
    )

    assert result.state is JobState.WARN
    assert {file.status for file in result.files} == {"warn"}
    assert {file.error_code for file in result.files} == {"backup_copy_failed"}


def test_source_disappearance_yields_failed(tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)

    from app.runtime import offload

    def missing_source(source_path: Path, target: Path) -> str:
        raise FileNotFoundError(f"missing {source_path}")

    monkeypatch.setattr(offload, "_copy_and_hash", missing_source)

    result = OffloadService(database).execute(
        job_id=job_id,
        source_root=source,
        plan=DestinationPlan(
            project_name="Project",
            main_root=tmp_path / "main",
            backup_root=tmp_path / "backup",
        ),
    )

    assert result.state is JobState.FAILED
    assert result.files[0].error_code == "main_copy_failed"
