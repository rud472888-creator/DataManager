from __future__ import annotations

import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.server import create_api_app
from app.config import Settings
from app.logging import configure_logging
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import PersistenceBundle
from app.runtime.agent import RuntimeAgent
from app.runtime.events import EventBus
from tests.support.fake_braw_adapters import fake_adapter_environment


class ReportApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.adapter_env = fake_adapter_environment(temp_path)
        self.adapter_env.__enter__()
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
        self.app = _build_test_app(settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.runtime = self.app.state.runtime_agent
        self.source_root = temp_path / "source_card"
        self.source_root.mkdir(parents=True, exist_ok=True)
        (self.source_root / "A001_C010.braw").write_bytes(b"r" * (1024 * 64))
        self.destination_volume_id = f"destination::{(temp_path / 'dest').resolve()}"
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
        self.adapter_env.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_reports_are_generated_and_downloadable_by_report_id(self) -> None:
        created = self.client.post(
            "/api/jobs",
            headers=self.auth_headers,
            json={
                "project_name": "Project Reports",
                "source_volume_id": f"source::{self.source_root.resolve()}",
                "dest_main_id": self.destination_volume_id,
                "policy": {"stub_mode": True},
            },
        )
        self.assertEqual(created.status_code, 201)
        job_id = created.json()["job_id"]
        self._wait_for_terminal_state(job_id)

        response = self.client.get(f"/api/jobs/{job_id}/reports", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual({item["report_type"] for item in items}, {"checksum_pdf", "image_pdf", "metadata_xlsx", "manifest_json"})

        manifest_item = next(item for item in items if item["report_type"] == "manifest_json")
        manifest_response = self.client.get(manifest_item["download_url"], headers=self.auth_headers)
        self.assertEqual(manifest_response.status_code, 200)
        self.assertEqual(manifest_response.headers["content-type"].split(";")[0], "application/json")
        manifest_payload = json.loads(manifest_response.content.decode("utf-8"))
        self.assertEqual(manifest_payload["job"]["job_id"], job_id)
        self.assertEqual(len(manifest_payload["reports"]), 4)

        xlsx_item = next(item for item in items if item["report_type"] == "metadata_xlsx")
        xlsx_response = self.client.get(xlsx_item["download_url"], headers=self.auth_headers)
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertEqual(
            xlsx_response.headers["content-type"].split(";")[0],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        xlsx_path = Path(self.temp_dir.name) / "downloaded-metadata.xlsx"
        xlsx_path.write_bytes(xlsx_response.content)
        with zipfile.ZipFile(xlsx_path) as workbook:
            self.assertIn("xl/worksheets/sheet1.xml", workbook.namelist())

        indexed_reports = self.runtime.persistence.reports.list_reports_for_job(job_id)
        self.assertEqual(len(indexed_reports), 4)

    def _wait_for_terminal_state(self, job_id: str, timeout: float = 5.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/jobs/{job_id}", headers=self.auth_headers)
            payload = response.json()
            if payload["state"] in {"COMPLETED", "WARN", "FAILED", "CANCELLED"}:
                return payload
            time.sleep(0.05)
        raise AssertionError(f"Job {job_id} did not reach a terminal state")


def _build_test_app(settings: Settings):
    settings.ensure_directories()
    configure_logging(settings.log_level)
    database = Database(settings.db_path)
    schema_path = Path(__file__).resolve().parents[3] / "app" / "persistence" / "schema.sql"
    apply_migrations(database, schema_path)
    persistence = PersistenceBundle(database)
    event_bus = EventBus()
    runtime_agent = RuntimeAgent(settings=settings, persistence=persistence, event_bus=event_bus)
    app = create_api_app(settings=settings, runtime_agent=runtime_agent, event_bus=event_bus)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_: object):
        await runtime_agent.startup()
        yield
        await runtime_agent.shutdown()

    app.router.lifespan_context = lifespan
    return app
