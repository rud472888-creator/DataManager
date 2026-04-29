import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.runtime.lifecycle import JobCreateRequest


@pytest.fixture()
def client(monkeypatch, tmp_path) -> TestClient:
    source = tmp_path / "source"
    source.mkdir()
    (source / "A001_C001.braw").write_bytes(b"clip")
    (source / "R001_C001.r3d").write_bytes(b"red")
    (source / "ALEXA_C001.ari").write_bytes(b"arri")
    (source / "ALEXA_C002.mxf").write_bytes(b"arri-mxf")
    monkeypatch.setenv("FDM_DATABASE_PATH", str(tmp_path / "fdm.sqlite3"))
    monkeypatch.setenv("FDM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FDM_DEV_SOURCE_ROOT", str(source))
    monkeypatch.setenv("FDM_ALLOWED_DEST_ROOTS", str(tmp_path / "main"))
    return TestClient(create_app())


def test_runtime_status_payload(client: TestClient) -> None:

    response = client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"] == "online"
    assert payload["platform"] == "macOS"
    assert payload["active_job_id"] is None
    assert payload["capabilities"]["checksum"] == "available"
    assert payload["capabilities"]["supported_offload_formats"] == ["BRAW", "R3D", "ARRIRAW"]
    assert payload["capabilities"]["supported_offload_suffixes"] == [
        ".ari",
        ".braw",
        ".mxf",
        ".r3d",
    ]
    assert payload["messages"][0] == "local runtime online"
    assert "clone" in payload["messages"][1]


def test_runtime_status_reports_persisted_active_job(client: TestClient) -> None:
    job = client.app.state.agent.lifecycle.create_job(
        JobCreateRequest(
            project_name="Status",
            source_volume_id="mock-source",
            dest_main_id="dest-0",
            dest_backup_id=None,
            operator_origin="test",
            policy={},
        )
    )

    response = client.get("/api/runtime/status")

    assert response.json()["active_job_id"] == job.job_id


def test_volumes_are_runtime_owned_mock_candidates(client: TestClient) -> None:
    response = client.get("/api/volumes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["volume_id"] == "mock-source"
    assert payload["destinations"][0]["volume_id"].startswith("dest-")


def test_console_home_shell_loads(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Footage Data Manager" in response.text
    assert "New offload job" in response.text
    assert "local runtime" in response.text
    assert "Loading runtime state" in response.text
    assert "Token is stored only in this browser session" in response.text


def test_runtime_websocket_stub(client: TestClient) -> None:
    with client.websocket_connect("/ws/runtime") as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "runtime_status"
    assert payload["event_id"].startswith("evt-")
    assert payload["runtime"] == "online"


def test_settings_requires_token(client: TestClient) -> None:
    unauthorized = client.get("/api/settings")
    authorized = client.get("/api/settings", headers={"Authorization": "Bearer change-me"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["token_required"] is True


def test_command_auth_and_decision(client: TestClient) -> None:
    job = client.app.state.agent.lifecycle.create_job(
        JobCreateRequest(
            project_name="API Test",
            source_volume_id="mock-source",
            dest_main_id="dest-0",
            dest_backup_id=None,
            operator_origin="remote_web",
            policy={},
        )
    )

    response = client.post(
        f"/api/jobs/{job.job_id}/command",
        headers={"Authorization": "Bearer change-me"},
        json={"command": "cancel", "operator_origin": "remote_web", "request_id": "cmd-test"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["state_before"] == "QUEUED"
    assert payload["state_after"] == "CANCELLED"


def test_server_import_does_not_create_default_database(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.api.server; "
            "from pathlib import Path; "
            "print(Path('.fdm_data/fdm.sqlite3').exists())",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    assert result.stdout.strip() == "False"
