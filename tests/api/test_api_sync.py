from fastapi.testclient import TestClient

from app.api.server import create_app
from app.persistence.models import Clip, JobFile, Report
from app.persistence.repositories import (
    ClipRepository,
    JobFileRepository,
    JobRepository,
    ReportRepository,
    deterministic_id,
)


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("FDM_DATABASE_PATH", str(tmp_path / "fdm.sqlite3"))
    monkeypatch.setenv("FDM_DATA_DIR", str(tmp_path / "data"))
    return TestClient(create_app())


def test_protected_routes_reject_missing_token(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/jobs",
        json={
            "project_name": "API",
            "source_volume_id": "mock-source",
            "dest_main_id": "dest-0",
            "dest_backup_id": None,
            "operator_origin": "remote_web",
            "policy": {},
        },
    )

    assert response.status_code == 401


def test_job_create_detail_command_and_logs(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/jobs",
        headers={"Authorization": "Bearer change-me"},
        json={
            "project_name": "API",
            "source_volume_id": "mock-source",
            "dest_main_id": "dest-0",
            "dest_backup_id": None,
            "operator_origin": "remote_web",
            "policy": {},
        },
    )
    job_id = created.json()["job"]["job_id"]
    rejected = client.post(
        f"/api/jobs/{job_id}/command",
        headers={"Authorization": "Bearer change-me"},
        json={"command": "resume", "operator_origin": "remote_web", "request_id": "cmd-1"},
    )
    detail = client.get(f"/api/jobs/{job_id}")
    logs = client.get(f"/api/jobs/{job_id}/logs")

    assert created.status_code == 200
    assert rejected.status_code == 200
    assert rejected.json()["accepted"] is False
    assert detail.json()["job"]["state"] == "QUEUED"
    assert any(
        event["command"] == "resume" and event["accepted"] is False
        for event in logs.json()["events"]
    )


def test_clips_reports_and_download_are_read_only(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    database = client.app.state.agent.database
    data_dir = client.app.state.agent.settings.data_dir
    artifact = data_dir / "00_master/reports/checksum.pdf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"%PDF test")

    with database.session() as connection:
        job = JobRepository(connection).create_stub_job("API Reports")
        clip = Clip(
            clip_id=deterministic_id("clip", job.job_id, "file-1"),
            job_id=job.job_id,
            file_id="file-1",
            format_name="BRAW",
            parser_version="mock",
            metadata_json='{"mock": true}',
            integrity_status="ok",
            capture_status="unavailable",
        )
        file_result = JobFile(
            file_id="file-1",
            job_id=job.job_id,
            source_relpath="A001/A001_C001.braw",
            size_bytes=8,
            status="verified",
        )
        report = Report(
            report_id=deterministic_id("report", job.job_id, "checksum_pdf"),
            job_id=job.job_id,
            report_type="checksum_pdf",
            artifact_relpath="00_master/reports/checksum.pdf",
            status="ready",
        )
        JobFileRepository(connection).upsert_result(file_result)
        ClipRepository(connection).upsert(clip)
        ReportRepository(connection).upsert(report)

    clips = client.get(f"/api/clips?job_id={job.job_id}")
    reports = client.get(f"/api/jobs/{job.job_id}/reports")
    download_url = reports.json()["reports"][0]["download_url"]
    downloaded = client.get(download_url)

    assert clips.status_code == 200
    assert clips.json()["clips"][0]["format_name"] == "BRAW"
    assert reports.status_code == 200
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF test"


def test_settings_patch_is_token_protected_and_filtered(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.patch(
        "/api/settings",
        headers={"Authorization": "Bearer change-me"},
        json={"ui_density": "compact", "arbitrary_path": "/tmp/nope"},
    )

    assert response.status_code == 200
    assert response.json()["settings"] == {"ui_density": "compact"}


def test_websocket_reconnect_status_snapshot(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    with client.websocket_connect("/ws/runtime") as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "runtime_status"
    assert payload["event_id"].startswith("evt-")
    assert payload["runtime"] == "online"
