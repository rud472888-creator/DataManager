from __future__ import annotations

import time
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        settings = Settings(
            host="127.0.0.1",
            port=4482,
            token="test-token",
            data_dir=temp_path / "data",
            db_path=temp_path / "data" / "fdm.sqlite3",
            logs_dir=temp_path / "data" / "logs",
            reports_dir=temp_path / "data" / "reports",
            temp_dir=temp_path / "data" / "tmp",
            allowed_destination_roots=(str(temp_path / "dest"),),
            log_level="INFO",
        )
        self.app = create_app(settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.runtime = self.app.state.runtime_agent
        self.source_root = Path(self.temp_dir.name) / "source_card"
        self.source_root.mkdir(parents=True, exist_ok=True)
        (self.source_root / "A001_C001.braw").write_bytes(b"x" * (1024 * 128))
        (self.source_root / ".DS_Store").write_text("ignore", encoding="utf-8")
        (self.source_root / "._noise").write_text("ignore", encoding="utf-8")
        self.destination_volume_id = f"destination::{(Path(self.temp_dir.name) / 'dest').resolve()}"
        self.runtime.persistence.volumes.upsert_volume(
            {
                "volume_id": f"source::{self.source_root.resolve()}",
                "display_name": "CARD_A",
                "mount_path": str(self.source_root.resolve()),
                "volume_role": "source",
                "is_removable": 1,
                "filesystem_type": None,
                "capacity_bytes": 100,
                "free_bytes": 50,
                "serial_hint": None,
                "approval_state": "detected",
                "last_seen_at": "2026-04-06T00:00:00+00:00",
                "metadata_json": "{}",
            }
        )
        self.auth_headers = {"Authorization": "Bearer test-token"}

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_runtime_status_and_job_roundtrip(self) -> None:
        response = self.client.get("/api/runtime/status", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

        volumes = self.client.get("/api/volumes", headers=self.auth_headers)
        self.assertEqual(volumes.status_code, 200)
        self.assertGreaterEqual(len(volumes.json()["items"]), 2)

        created = self.client.post(
            "/api/jobs",
            headers=self.auth_headers,
            json={
                "project_name": "Project Alpha",
                "source_volume_id": f"source::{self.source_root.resolve()}",
                "dest_main_id": self.destination_volume_id,
                "policy": {"stub_mode": True},
            },
        )
        self.assertEqual(created.status_code, 201)
        job_id = created.json()["job_id"]
        terminal_job = self._wait_for_terminal_state(job_id)
        self.assertEqual(terminal_job["state"], "WARN")
        self.assertEqual(terminal_job["stats"]["processed_files"], 1)

        listed = self.client.get("/api/jobs", headers=self.auth_headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

        command = self.client.post(
            f"/api/jobs/{job_id}/command",
            headers=self.auth_headers,
            json={"command": "retry"},
        )
        self.assertEqual(command.status_code, 200)
        self.assertTrue(command.json()["accepted"])

    def test_websocket_receives_job_event(self) -> None:
        with self.client.websocket_connect("/ws/events", headers=self.auth_headers) as websocket:
            created = self.client.post(
                "/api/jobs",
                headers=self.auth_headers,
                json={
                    "project_name": "Project Beta",
                    "source_volume_id": f"source::{self.source_root.resolve()}",
                    "dest_main_id": self.destination_volume_id,
                    "policy": {"stub_mode": True},
                },
            )
            self.assertEqual(created.status_code, 201)
            seen_types: set[str] = set()
            for _ in range(8):
                event = websocket.receive_json()
                seen_types.add(event["type"])
                if "job.progress" in seen_types and "job.state_changed" in seen_types:
                    break
            self.assertIn("job.created", seen_types)
            self.assertIn("job.state_changed", seen_types)
            self.assertIn("job.progress", seen_types)

    def test_cancel_running_job(self) -> None:
        large_source = self.source_root / "A002_C002.braw"
        large_source.write_bytes(b"y" * (1024 * 1024 * 64))
        created = self.client.post(
            "/api/jobs",
            headers=self.auth_headers,
            json={
                "project_name": "Project Gamma",
                "source_volume_id": f"source::{self.source_root.resolve()}",
                "dest_main_id": self.destination_volume_id,
                "policy": {"stub_mode": True},
            },
        )
        self.assertEqual(created.status_code, 201)
        job_id = created.json()["job_id"]
        self._wait_for_state(job_id, {"COPYING"})
        cancelled = self.client.post(
            f"/api/jobs/{job_id}/command",
            headers=self.auth_headers,
            json={"command": "cancel"},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertTrue(cancelled.json()["accepted"])
        terminal = self._wait_for_state(job_id, {"CANCELLED", "WARN", "FAILED"})
        self.assertEqual(terminal["state"], "CANCELLED")

    def _wait_for_state(self, job_id: str, states: set[str], timeout: float = 5.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/jobs/{job_id}", headers=self.auth_headers)
            payload = response.json()
            if payload["state"] in states:
                return payload
            time.sleep(0.05)
        raise AssertionError(f"Job {job_id} did not reach one of {states}")

    def _wait_for_terminal_state(self, job_id: str) -> dict[str, object]:
        return self._wait_for_state(job_id, {"WARN", "FAILED", "CANCELLED"})
