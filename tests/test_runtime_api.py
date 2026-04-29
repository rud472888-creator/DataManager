import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app


@pytest.fixture()
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("FDM_DATABASE_PATH", str(tmp_path / "fdm.sqlite3"))
    monkeypatch.setenv("FDM_DATA_DIR", str(tmp_path / "data"))
    return TestClient(create_app())


def test_runtime_status_payload(client: TestClient) -> None:

    response = client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"] == "online"
    assert payload["platform"] == "macOS"
    assert payload["active_job_id"] is None
    assert payload["capabilities"]["checksum"] == "available"
    assert payload["capabilities"]["braw_metadata"] == "unavailable"
    assert payload["capabilities"]["braw_frame_capture"] == "unavailable"
    assert "foundation" in payload["messages"][0]


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
    created = client.post(
        "/api/jobs",
        headers={"Authorization": "Bearer change-me"},
        json={
            "project_name": "API Test",
            "source_volume_id": "mock-source",
            "dest_main_id": "dest-0",
            "dest_backup_id": None,
            "operator_origin": "remote_web",
            "policy": {},
        },
    )
    job_id = created.json()["job"]["job_id"]

    response = client.post(
        f"/api/jobs/{job_id}/command",
        headers={"Authorization": "Bearer change-me"},
        json={"command": "cancel", "operator_origin": "remote_web", "request_id": "cmd-test"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["state_before"] == "QUEUED"
    assert payload["state_after"] == "CANCELLED"
