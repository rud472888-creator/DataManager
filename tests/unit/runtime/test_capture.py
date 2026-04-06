from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import PersistenceBundle
from app.runtime.capture import FrameCaptureService
from tests.support.fake_braw_adapters import fake_adapter_environment


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.adapter_env = fake_adapter_environment(temp_path)
        self.adapter_env.__enter__()
        self.database = Database(temp_path / "test.sqlite3")
        schema_path = Path(__file__).resolve().parents[3] / "app" / "persistence" / "schema.sql"
        apply_migrations(self.database, schema_path)
        self.persistence = PersistenceBundle(self.database)

    def tearDown(self) -> None:
        self.adapter_env.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_capture_service_persists_real_outputs(self) -> None:
        self.persistence.jobs.create_job(
            {
                "job_id": "JOB-CAPTURE-001",
                "retry_of_job_id": None,
                "project_name": "Project Capture",
                "source_volume_id": "source::/Volumes/CARD_A",
                "dest_main_id": "destination::/tmp/DEST",
                "dest_backup_id": None,
                "state": "COPYING",
                "current_step": "copying",
                "resume_step": None,
                "operator_origin": "test",
                "policy_json": {},
                "stats_json": {"stubbed": False},
                "warning_count": 0,
                "error_count": 0,
                "current_file_relpath": None,
            }
        )
        self.persistence.job_files.replace_for_job(
            "JOB-CAPTURE-001",
            [{"relative_path": "A001_C010.braw", "size_bytes": 12, "metadata": {}, "has_backup": False}],
        )
        job_file = self.persistence.job_files.list_for_job("JOB-CAPTURE-001")[0]
        source = Path(self.temp_dir.name) / "A001_C010.braw"
        source.write_bytes(b"braw")
        output_root = Path(self.temp_dir.name) / "captures"

        result = FrameCaptureService(self.database).capture_file(
            job_file_id=job_file.job_file_id,
            relative_path=job_file.relative_path,
            source_path=str(source),
            output_root=output_root,
            indices=[0, 50, 100],
        )

        self.assertEqual(result["capture_state"], "CAPTURED")
        self.assertEqual(len(result["frames"]), 3)
        persisted = self.persistence.job_files.list_for_job("JOB-CAPTURE-001")[0]
        self.assertEqual(persisted.capture_state, "CAPTURED")
