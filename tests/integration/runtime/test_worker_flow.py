from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.main import build_runtime


class WorkerFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.source_root = temp_path / "source_card"
        self.source_root.mkdir(parents=True, exist_ok=True)
        (self.source_root / "A001_C003.braw").write_bytes(b"z" * (1024 * 256))
        self.settings = Settings(
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
        self.runtime, self.event_bus = build_runtime(self.settings)
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
        await self.runtime.startup()

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()
        self.temp_dir.cleanup()

    async def test_worker_scans_and_copies(self) -> None:
        created = await self.runtime.create_job(
            project_name="Project Delta",
            source_volume_id=f"source::{self.source_root.resolve()}",
            dest_main_id=f"destination::{(Path(self.temp_dir.name) / 'dest').resolve()}",
            dest_backup_id=None,
            policy={},
            origin="test",
        )
        job_id = created["job_id"]
        for _ in range(100):
            job = self.runtime.get_job(job_id)
            assert job is not None
            if job["state"] in {"WARN", "FAILED"}:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(job["state"], "WARN")
        self.assertEqual(job["stats"]["processed_files"], 1)
        job_file = self.runtime.persistence.job_files.list_for_job(job_id)[0]
        self.assertEqual(job_file.verify_main_state, "VERIFIED")
        self.assertEqual(job_file.verify_backup_state, "SKIPPED")
        self.assertIsNotNone(job_file.source_checksum_sha256)
        self.assertEqual(job_file.source_checksum_sha256, job_file.main_checksum_sha256)
        copied = Path(self.temp_dir.name) / "dest" / "Project_Delta" / "01_footage" / "CARD_A" / "A001_C003.braw"
        self.assertTrue(copied.exists())

    async def test_retry_command_creates_follow_up_job(self) -> None:
        created = await self.runtime.create_job(
            project_name="Project Retry",
            source_volume_id=f"source::{self.source_root.resolve()}",
            dest_main_id=f"destination::{(Path(self.temp_dir.name) / 'dest').resolve()}",
            dest_backup_id=None,
            policy={},
            origin="remote_web",
        )
        job_id = created["job_id"]
        for _ in range(100):
            job = self.runtime.get_job(job_id)
            assert job is not None
            if job["state"] in {"WARN", "FAILED"}:
                break
            await asyncio.sleep(0.05)

        result = await self.runtime.handle_command(
            job_id=job_id,
            command_name="retry",
            origin="remote_web",
        )
        self.assertTrue(result.accepted)

        jobs = self.runtime.list_jobs()
        self.assertEqual(len(jobs), 2)
        retry_job = next(item for item in jobs if item["job_id"] != job_id)
        self.assertEqual(retry_job["retry_of_job_id"], job_id)
        self.assertEqual(retry_job["state"], "QUEUED")
        self.assertEqual(retry_job["operator_origin"], "remote_web")
