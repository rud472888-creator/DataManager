from pathlib import Path

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import JobFileRepository, JobRepository
from app.runtime.offload import DestinationPlan, OffloadService, ReplicaPath, SourcePath
from app.runtime.state_machine import JobState


def test_web_console_static_surface_is_removed() -> None:
    assert not Path("app/web_console").exists()


def test_migrations_are_idempotent(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    with database.session() as connection:
        apply_migrations(connection)
        apply_migrations(connection)
        versions = connection.execute("SELECT COUNT(*) AS count FROM schema_version").fetchone()

    assert versions["count"] == 1


def test_large_fixture_offload_smoke(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job("Large Fixture")
    source = tmp_path / "source"
    source.mkdir()
    for index in range(50):
        (source / f"A001_C{index:03}.braw").write_bytes(f"clip-{index}".encode())

    result = OffloadService(database).execute(
        job_id=job.job_id,
        source_paths=(SourcePath("path1", source),),
        plan=DestinationPlan(
            "Large Fixture",
            (
                ReplicaPath("path1", tmp_path / "path1"),
                ReplicaPath("path2", tmp_path / "path2"),
            ),
        ),
    )

    with database.session() as connection:
        files = JobFileRepository(connection).list_for_job(job.job_id)

    assert result.state is JobState.COMPLETED
    assert len(files) == 50


def test_invalid_command_and_settings_path_filter(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FDM_DATABASE_PATH", str(tmp_path / "fdm.sqlite3"))
    monkeypatch.setenv("FDM_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())
    created = client.post(
        "/api/jobs",
        headers={"Authorization": "Bearer change-me"},
        json={
            "project_name": "Hardening",
            "source_path_ids": ["mock-source"],
            "replica_path_ids": ["dest-0"],
            "operator_origin": "remote_web",
            "policy": {},
        },
    )
    job_id = created.json()["job"]["job_id"]
    invalid = client.post(
        f"/api/jobs/{job_id}/command",
        headers={"Authorization": "Bearer change-me"},
        json={"command": "erase", "operator_origin": "remote_web", "request_id": "bad"},
    )
    settings = client.patch(
        "/api/settings",
        headers={"Authorization": "Bearer change-me"},
        json={"operator_name": "op", "allowed_dest_root": "/tmp/unsafe"},
    )

    assert invalid.status_code == 400
    assert settings.json()["settings"] == {"operator_name": "op"}


def test_console_accessibility_affordances_moved_to_orchestrator() -> None:
    assert not Path("app/web_console/index.html").exists()
