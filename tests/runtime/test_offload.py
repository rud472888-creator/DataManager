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
    (root / "R001").mkdir(parents=True)
    (root / "R001" / "R001_C001.r3d").write_bytes(b"red-raw")
    (root / "ARRI").mkdir(parents=True)
    (root / "ARRI" / "ALEXA_C001.ari").write_bytes(b"arriraw-ari")
    (root / "ARRI" / "ALEXA_C002.mxf").write_bytes(b"arriraw-mxf")
    (root / "Video").mkdir(parents=True)
    (root / "Video" / "B001_C001.mov").write_bytes(b"quicktime")
    (root / "Video" / "B001_C002.mp4").write_bytes(b"mpeg-4")
    (root / "notes.txt").write_bytes(b"unsupported")
    (root / ".DS_Store").write_bytes(b"ignored")
    (root / "._A001_C003.braw").write_bytes(b"ignored")


def test_scan_source_filters_supported_files(tmp_path) -> None:
    source = tmp_path / "source"
    _write_source(source)

    files = scan_source(source)

    assert [file.relpath.as_posix() for file in files] == [
        "A001/A001_C001.braw",
        "A001/A001_C002.braw",
        "ARRI/ALEXA_C001.ari",
        "ARRI/ALEXA_C002.mxf",
        "R001/R001_C001.r3d",
        "Video/B001_C001.mov",
        "Video/B001_C002.mp4",
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
    assert (tmp_path / "main/Project/01_Footage/R#1/A001/A001_C001.braw").exists()
    assert (tmp_path / "main/Project/01_Footage/R#1/R001/R001_C001.r3d").exists()
    assert (tmp_path / "main/Project/01_Footage/R#1/ARRI/ALEXA_C001.ari").exists()
    assert (tmp_path / "main/Project/01_Footage/R#1/ARRI/ALEXA_C002.mxf").exists()
    assert (tmp_path / "main/Project/01_Footage/R#1/Video/B001_C001.mov").exists()
    assert (tmp_path / "main/Project/01_Footage/R#1/Video/B001_C002.mp4").exists()
    assert (tmp_path / "backup/Project/01_Footage/R#1/A001/A001_C002.braw").exists()
    assert (tmp_path / "main/Project/00_Master/reports").is_dir()
    assert (tmp_path / "main/Project/02_Comp").is_dir()
    assert (tmp_path / "main/Project/03_2D_Design").is_dir()
    assert (tmp_path / "main/Project/04_Color").is_dir()
    assert (tmp_path / "main/Project/05_Sound").is_dir()
    assert (tmp_path / "main/Project/06_FIN").is_dir()
    assert (tmp_path / "main/Project/07_ETC_DATA").is_dir()

    with database.session() as connection:
        job = JobRepository(connection).get(job_id)
        files = JobFileRepository(connection).list_for_job(job_id)

    assert job is not None
    assert job.state == "COMPLETED"
    assert len(files) == 7
    assert {file.status for file in files} == {"verified"}
    assert all(file.checksum_source == file.checksum_main == file.checksum_backup for file in files)


def test_collision_blocks_blind_overwrite(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)
    collision = tmp_path / "main/Project/01_Footage/R#1/A001/A001_C001.braw"
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"existing")

    result = OffloadService(database).execute(
        job_id=job_id,
        source_root=source,
        plan=DestinationPlan(
            project_name="Project",
            main_root=tmp_path / "main",
            backup_root=tmp_path / "backup",
            footage_run_name="R#1",
        ),
    )

    assert result.state is JobState.FAILED
    assert "collision" in result.reason
    assert collision.read_bytes() == b"existing"


def test_existing_run_folder_advances_next_backup_round(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)
    (tmp_path / "main/Project/01_Footage/R#1").mkdir(parents=True)
    (tmp_path / "backup/Project/01_Footage/R#2").mkdir(parents=True)

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
    assert (tmp_path / "main/Project/01_Footage/R#3/A001/A001_C001.braw").exists()
    assert (tmp_path / "backup/Project/01_Footage/R#3/A001/A001_C001.braw").exists()


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
