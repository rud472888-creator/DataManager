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
    scan_root = tmp_path / "Volumes"
    source = scan_root / "CameraCard"
    source.mkdir(parents=True)
    (source / "A001_C001.braw").write_bytes(b"clip")
    (source / "R001_C001.r3d").write_bytes(b"red")
    (source / "ALEXA_C001.ari").write_bytes(b"arri")
    (source / "ALEXA_C002.mxf").write_bytes(b"arri-mxf")
    (source / "B001_C001.mov").write_bytes(b"quicktime")
    (source / "B001_C002.mp4").write_bytes(b"mpeg-4")
    (scan_root / "ReplicaRAID").mkdir()
    (scan_root / ".timemachine").mkdir()
    (scan_root / "Macintosh HD").mkdir()
    monkeypatch.setenv("FDM_DATABASE_PATH", str(tmp_path / "fdm.sqlite3"))
    monkeypatch.setenv("FDM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FDM_VOLUME_SCAN_ROOT", str(scan_root))
    monkeypatch.setenv("FDM_ALLOWED_DEST_ROOTS", str(tmp_path / "replica"))
    return TestClient(create_app())


def _volume_ids(client: TestClient) -> tuple[str, str]:
    payload = client.get("/api/volumes").json()
    return payload["sources"][0]["volume_id"], payload["destinations"][0]["volume_id"]


def test_runtime_status_payload(client: TestClient) -> None:

    response = client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"] == "online"
    assert payload["platform"] == "macOS"
    assert payload["active_job_id"] is None
    assert payload["capabilities"]["checksum"] == "available"
    assert payload["capabilities"]["supported_offload_formats"] == [
        "BRAW",
        "R3D",
        "ARRIRAW",
        "STANDARD_VIDEO",
    ]
    assert payload["capabilities"]["supported_offload_suffixes"] == [
        ".ari",
        ".braw",
        ".mov",
        ".mp4",
        ".mxf",
        ".r3d",
    ]
    assert payload["messages"][0] == "local runtime online"
    assert "clone" in payload["messages"][1]


def test_runtime_status_reports_persisted_active_job(client: TestClient) -> None:
    source_id, replica_id = _volume_ids(client)
    job = client.app.state.agent.lifecycle.create_job(
        JobCreateRequest(
            project_name="Status",
            source_path_ids=(source_id,),
            replica_path_ids=(replica_id,),
            operator_origin="test",
            policy={},
        )
    )

    response = client.get("/api/runtime/status")

    assert response.json()["active_job_id"] == job.job_id


def test_volumes_are_runtime_owned_candidates(client: TestClient) -> None:
    response = client.get("/api/volumes")

    assert response.status_code == 200
    payload = response.json()
    source_ids = {volume["volume_id"] for volume in payload["sources"]}
    destination_ids = {volume["volume_id"] for volume in payload["destinations"]}
    all_paths = {volume["display_path"] for volume in payload["sources"] + payload["destinations"]}

    assert "src-cameracard" in source_ids
    assert "dest-replicaraid" in destination_ids
    assert not any(path.endswith(".timemachine") for path in all_paths)
    assert not any(path.endswith("Macintosh HD") for path in all_paths)
    assert all(
        volume["bytes_available"] is None or isinstance(volume["bytes_available"], int)
        for volume in payload["sources"] + payload["destinations"]
    )


def test_console_home_shell_is_removed(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 404


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
    source_id, replica_id = _volume_ids(client)
    job = client.app.state.agent.lifecycle.create_job(
        JobCreateRequest(
            project_name="API Test",
            source_path_ids=(source_id,),
            replica_path_ids=(replica_id,),
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
