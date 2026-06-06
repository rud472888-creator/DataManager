from fastapi.testclient import TestClient

from app.api.server import create_app
from app.local_panel.minimal_panel import render_panel
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import JobRepository
from app.runtime.lifecycle import JobCreateRequest
from app.runtime.offload import DestinationPlan, OffloadService, ReplicaPath, SourcePath
from app.runtime.state_machine import JobState


def test_runtime_restart_loads_recoverable_jobs(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "fdm.sqlite3"
    monkeypatch.setenv("FDM_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("FDM_DATA_DIR", str(tmp_path / "data"))
    first = create_app()
    first.state.agent.lifecycle.create_job(
        JobCreateRequest(
            project_name="Recover",
            source_path_ids=("mock-source",),
            replica_path_ids=("dest-0",),
            operator_origin="test",
            policy={},
        )
    )

    restarted = TestClient(create_app())
    recovery = restarted.get("/api/runtime/recovery")

    assert recovery.status_code == 200
    assert recovery.json()["jobs"][0]["state"] == "QUEUED"


def test_log_parity_for_command_rejection(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FDM_DATABASE_PATH", str(tmp_path / "fdm.sqlite3"))
    monkeypatch.setenv("FDM_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())
    created = client.post(
        "/api/jobs",
        headers={"Authorization": "Bearer change-me"},
        json={
            "project_name": "Parity",
            "source_path_ids": ["mock-source"],
            "replica_path_ids": ["dest-0"],
            "operator_origin": "remote_web",
            "policy": {},
        },
    )
    job_id = created.json()["job"]["job_id"]
    command = client.post(
        f"/api/jobs/{job_id}/command",
        headers={"Authorization": "Bearer change-me"},
        json={"command": "resume", "operator_origin": "remote_web", "request_id": "cmd"},
    )
    logs = client.get(f"/api/jobs/{job_id}/logs")

    assert command.json()["accepted"] is False
    assert any(
        event["command"] == "resume" and event["accepted"] is False
        for event in logs.json()["events"]
    )


def test_replica_failure_path_remains_warn(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")
    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job()
    source = tmp_path / "source"
    source.mkdir()
    (source / "A001_C001.braw").write_bytes(b"clip")

    from app.runtime import offload

    original = offload._copy_and_hash

    def fail_replica(source_path, target):
        if "path2" in target.parts:
            raise OSError("replica disconnected")
        return original(source_path, target)

    offload._copy_and_hash = fail_replica
    try:
        result = OffloadService(database).execute(
            job_id=job.job_id,
            source_paths=(SourcePath("path1", source),),
            plan=DestinationPlan(
                "Recover",
                (
                    ReplicaPath("path1", tmp_path / "path1"),
                    ReplicaPath("path2", tmp_path / "path2"),
                ),
            ),
        )
    finally:
        offload._copy_and_hash = original

    assert result.state is JobState.WARN


def test_local_panel_remains_status_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FDM_DATABASE_PATH", str(tmp_path / "fdm.sqlite3"))
    app = create_app()

    html = render_panel(app.state.agent)

    assert "Local Panel" in html
    assert "not a file executor" in html
    assert 'input type="file"' not in html
