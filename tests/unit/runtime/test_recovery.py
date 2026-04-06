from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import PersistenceBundle
from app.runtime.recovery import RecoveryManager
from app.runtime.state_machine import JobState


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.database = Database(temp_path / "test.sqlite3")
        schema_path = Path(__file__).resolve().parents[3] / "app" / "persistence" / "schema.sql"
        apply_migrations(self.database, schema_path)
        self.persistence = PersistenceBundle(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_recovery_marks_in_progress_work_failed_and_removes_partial_files(self) -> None:
        self.persistence.jobs.create_job(
            {
                "job_id": "JOB-RECOVERY-001",
                "retry_of_job_id": None,
                "project_name": "Project Recovery",
                "source_volume_id": "source::/Volumes/CARD_A",
                "dest_main_id": "destination::/tmp/DEST",
                "dest_backup_id": None,
                "state": JobState.COPYING.value,
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
            "JOB-RECOVERY-001",
            [
                {"relative_path": "A001_C001.braw", "size_bytes": 16, "metadata": {}, "has_backup": True},
                {"relative_path": "A001_C002.braw", "size_bytes": 16, "metadata": {}, "has_backup": False},
            ],
        )
        copy_file, verify_file = self.persistence.job_files.list_for_job("JOB-RECOVERY-001")
        partial_main = Path(self.temp_dir.name) / "main.fdm-partial"
        partial_backup = Path(self.temp_dir.name) / "backup.fdm-partial"
        partial_main.write_text("partial", encoding="utf-8")
        partial_backup.write_text("partial", encoding="utf-8")
        self.persistence.job_files.update_copy_state(
            job_file_id=copy_file.job_file_id,
            main_state="IN_PROGRESS",
            backup_state="IN_PROGRESS",
            metadata={
                "main_temp_path": str(partial_main),
                "backup_temp_path": str(partial_backup),
            },
        )
        self.persistence.job_files.update_verify_state(
            job_file_id=verify_file.job_file_id,
            verify_main_state="IN_PROGRESS",
        )

        recovered = RecoveryManager(self.persistence.jobs, self.persistence.job_files).recover_interrupted_jobs()

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["affected_job_files"], 2)
        self.assertEqual(recovered[0]["removed_partial_files"], 2)
        self.assertFalse(partial_main.exists())
        self.assertFalse(partial_backup.exists())
        job = self.persistence.jobs.get_job("JOB-RECOVERY-001")
        assert job is not None
        self.assertEqual(job.state, "FAILED")
        updated_copy, updated_verify = self.persistence.job_files.list_for_job("JOB-RECOVERY-001")
        self.assertEqual(updated_copy.copy_main_state, "FAILED")
        self.assertEqual(updated_copy.copy_backup_state, "FAILED")
        self.assertEqual(updated_verify.verify_main_state, "FAILED")
