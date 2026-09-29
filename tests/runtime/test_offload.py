from pathlib import Path

from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import JobFileRepository, JobRepository
from app.runtime.offload import DestinationPlan, OffloadService, ReplicaPath, SourcePath
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


def test_flat_card_layout_copies_contents_directly_and_preserves_source_subfolders(tmp_path):
    database = Database(tmp_path / "flat.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "card"
    (source / "CLIPS").mkdir(parents=True)
    (source / "A001.mov").write_bytes(b"root clip")
    (source / "CLIPS/A002.mov").write_bytes(b"nested clip")
    destination = tmp_path / "backup"
    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(SourcePath(path_id="source-path-1", root=source),),
        plan=DestinationPlan(
            project_name="Film", replica_paths=(ReplicaPath(path_id="replica-1", root=destination),),
            footage_run_name="R#3", flat_card_layout=True,
        ),
    )
    assert result.state is JobState.COMPLETED
    roll = destination / "Film/001_Footage/R#3"
    assert (roll / "A001.mov").read_bytes() == b"root clip"
    assert (roll / "CLIPS/A002.mov").read_bytes() == b"nested clip"
    assert not (roll / "source-path-1").exists()
    assert not (destination / "Film/01_Footage").exists()
    assert {r.dest_relpath for f in result.files for r in f.replica_results} == {
        "001_Footage/R#3/A001.mov", "001_Footage/R#3/CLIPS/A002.mov",
    }


def test_offload_replicates_n_sources_to_n_equal_replica_paths(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source_a = tmp_path / "card-a"
    source_b = tmp_path / "card-b"
    (source_a / "A001").mkdir(parents=True)
    (source_a / "A001" / "A001_C001.braw").write_bytes(b"clip-a")
    (source_b / "B001").mkdir(parents=True)
    (source_b / "B001" / "B001_C001.braw").write_bytes(b"clip-b")

    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(
            SourcePath(path_id="path1", root=source_a),
            SourcePath(path_id="path2", root=source_b),
        ),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(
                ReplicaPath(path_id="path1", root=tmp_path / "replica-1"),
                ReplicaPath(path_id="path2", root=tmp_path / "replica-2"),
                ReplicaPath(path_id="path3", root=tmp_path / "replica-3"),
            ),
        ),
    )

    assert result.state is JobState.COMPLETED
    for replica in ("replica-1", "replica-2", "replica-3"):
        assert (tmp_path / replica / "Project/01_Footage/R#1/path1/A001/A001_C001.braw").exists()
        assert (tmp_path / replica / "Project/01_Footage/R#1/path2/B001/B001_C001.braw").exists()

    with database.session() as connection:
        files = JobFileRepository(connection).list_for_job(job_id)

    assert len(files) == 2
    assert {file.source_path_id for file in files} == {"path1", "path2"}
    assert all(len(file.replica_results) == 3 for file in files)
    assert all(
        {replica.path_id for replica in file.replica_results} == {"path1", "path2", "path3"}
        for file in files
    )


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


def test_offload_success_copies_to_equal_replica_paths_and_persists_results(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)

    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(SourcePath(path_id="path1", root=source),),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(
                ReplicaPath(path_id="path1", root=tmp_path / "path1"),
                ReplicaPath(path_id="path2", root=tmp_path / "path2"),
            ),
        ),
    )

    assert result.state is JobState.COMPLETED
    assert (tmp_path / "path1/Project/01_Footage/R#1/path1/A001/A001_C001.braw").exists()
    assert (tmp_path / "path1/Project/01_Footage/R#1/path1/R001/R001_C001.r3d").exists()
    assert (tmp_path / "path1/Project/01_Footage/R#1/path1/ARRI/ALEXA_C001.ari").exists()
    assert (tmp_path / "path1/Project/01_Footage/R#1/path1/ARRI/ALEXA_C002.mxf").exists()
    assert (tmp_path / "path1/Project/01_Footage/R#1/path1/Video/B001_C001.mov").exists()
    assert (tmp_path / "path1/Project/01_Footage/R#1/path1/Video/B001_C002.mp4").exists()
    assert (tmp_path / "path2/Project/01_Footage/R#1/path1/A001/A001_C002.braw").exists()
    assert (tmp_path / "path1/Project/00_Master/reports").is_dir()
    assert (tmp_path / "path1/Project/02_Comp").is_dir()
    assert (tmp_path / "path1/Project/03_2D_Design").is_dir()
    assert (tmp_path / "path1/Project/04_Color").is_dir()
    assert (tmp_path / "path1/Project/05_Sound").is_dir()
    assert (tmp_path / "path1/Project/06_FIN").is_dir()
    assert (tmp_path / "path1/Project/07_ETC_DATA").is_dir()

    with database.session() as connection:
        job = JobRepository(connection).get(job_id)
        files = JobFileRepository(connection).list_for_job(job_id)

    assert job is not None
    assert job.state == "COMPLETED"
    assert len(files) == 7
    assert {file.status for file in files} == {"verified"}
    assert all(
        file.checksum_source == replica.checksum
        for file in files
        for replica in file.replica_results
    )


def test_metadata_copy_permission_error_does_not_fail_verified_content(
    tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    source.mkdir()
    (source / "A001_C001.braw").write_bytes(b"clip")

    from app.runtime import offload

    def denied_metadata_copy(source_path: Path, target: Path) -> None:
        raise PermissionError(f"metadata denied: {target}")

    monkeypatch.setattr(offload.shutil, "copystat", denied_metadata_copy)

    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(SourcePath(path_id="path1", root=source),),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(ReplicaPath(path_id="path1", root=tmp_path / "path1"),),
        ),
    )

    replica = tmp_path / "path1/Project/01_Footage/R#1/path1/A001_C001.braw"
    assert result.state is JobState.COMPLETED
    assert replica.read_bytes() == b"clip"
    assert result.files[0].status == "verified"
    assert result.files[0].checksum_source == result.files[0].replica_results[0].checksum


def test_collision_blocks_blind_overwrite(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)
    collision = tmp_path / "path1/Project/01_Footage/R#1/path1/A001/A001_C001.braw"
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"existing")

    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(SourcePath(path_id="path1", root=source),),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(
                ReplicaPath(path_id="path1", root=tmp_path / "path1"),
                ReplicaPath(path_id="path2", root=tmp_path / "path2"),
            ),
            footage_run_name="R#1",
        ),
    )

    assert result.state is JobState.FAILED
    assert "collision" in result.reason
    assert collision.read_bytes() == b"existing"


def test_existing_verified_target_is_reused_for_retry(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    source.mkdir()
    (source / "A001_C001.braw").write_bytes(b"clip")
    existing = tmp_path / "path1/Project/01_Footage/R#1/path1/A001_C001.braw"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"clip")

    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(SourcePath(path_id="path1", root=source),),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(ReplicaPath(path_id="path1", root=tmp_path / "path1"),),
            footage_run_name="R#1",
        ),
    )

    assert result.state is JobState.COMPLETED
    assert result.files[0].status == "verified"
    assert existing.read_bytes() == b"clip"


def test_existing_run_folder_advances_next_replica_round(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)
    (tmp_path / "path1/Project/01_Footage/R#1").mkdir(parents=True)
    (tmp_path / "path2/Project/01_Footage/R#2").mkdir(parents=True)

    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(SourcePath(path_id="path1", root=source),),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(
                ReplicaPath(path_id="path1", root=tmp_path / "path1"),
                ReplicaPath(path_id="path2", root=tmp_path / "path2"),
            ),
        ),
    )

    assert result.state is JobState.COMPLETED
    assert (tmp_path / "path1/Project/01_Footage/R#3/path1/A001/A001_C001.braw").exists()
    assert (tmp_path / "path2/Project/01_Footage/R#3/path1/A001/A001_C001.braw").exists()


def test_replica_failure_yields_warn_after_other_replica_success(tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    job_id = _make_job(database)
    source = tmp_path / "source"
    _write_source(source)

    from app.runtime import offload

    original = offload._copy_and_hash

    def flaky_replica(source_path: Path, target: Path) -> str:
        if "path2" in target.parts:
            raise OSError("replica device unavailable")
        return original(source_path, target)

    monkeypatch.setattr(offload, "_copy_and_hash", flaky_replica)

    result = OffloadService(database).execute(
        job_id=job_id,
        source_paths=(SourcePath(path_id="path1", root=source),),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(
                ReplicaPath(path_id="path1", root=tmp_path / "path1"),
                ReplicaPath(path_id="path2", root=tmp_path / "path2"),
            ),
        ),
    )

    assert result.state is JobState.WARN
    assert {file.status for file in result.files} == {"warn"}
    assert {file.error_code for file in result.files} == {"replica_incomplete"}


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
        source_paths=(SourcePath(path_id="path1", root=source),),
        plan=DestinationPlan(
            project_name="Project",
            replica_paths=(
                ReplicaPath(path_id="path1", root=tmp_path / "path1"),
                ReplicaPath(path_id="path2", root=tmp_path / "path2"),
            ),
        ),
    )

    assert result.state is JobState.FAILED
    assert result.files[0].error_code == "replica_copy_failed"
