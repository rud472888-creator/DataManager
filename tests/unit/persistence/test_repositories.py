from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import PersistenceBundle
from app.runtime.state_machine import JobCommand, JobState


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.database = Database(temp_path / "test.sqlite3")
        schema_path = Path(__file__).resolve().parents[3] / "app" / "persistence" / "schema.sql"
        apply_migrations(self.database, schema_path)
        self.persistence = PersistenceBundle(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_job_create_and_command_event_persist(self) -> None:
        self.persistence.volumes.upsert_volume(
            {
                "volume_id": "source::/Volumes/CARD_A",
                "display_name": "CARD_A",
                "mount_path": "/Volumes/CARD_A",
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
        self.persistence.volumes.upsert_volume(
            {
                "volume_id": "destination::/tmp/DEST",
                "display_name": "DEST",
                "mount_path": "/tmp/DEST",
                "volume_role": "destination",
                "is_removable": 0,
                "filesystem_type": None,
                "capacity_bytes": 100,
                "free_bytes": 50,
                "serial_hint": None,
                "approval_state": "approved",
                "last_seen_at": "2026-04-06T00:00:00+00:00",
                "metadata_json": "{}",
            }
        )
        job = self.persistence.jobs.create_job(
            {
                "job_id": "JOB-TEST-001",
                "retry_of_job_id": None,
                "project_name": "Project Alpha",
                "source_volume_id": "source::/Volumes/CARD_A",
                "dest_main_id": "destination::/tmp/DEST",
                "dest_backup_id": None,
                "state": JobState.QUEUED.value,
                "current_step": "queued",
                "resume_step": None,
                "operator_origin": "test",
                "policy_json": {},
                "stats_json": {"stubbed": True},
                "warning_count": 0,
                "error_count": 0,
                "current_file_relpath": None,
            }
        )
        self.assertEqual(job.job_id, "JOB-TEST-001")
        event_id = self.persistence.jobs.append_command_result(
            job_id=job.job_id,
            command=JobCommand.CANCEL,
            accepted=True,
            message="cancel accepted",
            origin="test",
            payload={"state": JobState.QUEUED.value},
        )
        self.assertGreater(event_id, 0)
        events = self.persistence.events.list_events_for_job(job.job_id)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].command_name, "cancel")

    def test_mark_in_progress_as_failed_covers_copy_and_verify_states(self) -> None:
        self.persistence.jobs.create_job(
            {
                "job_id": "JOB-TEST-VERIFY",
                "retry_of_job_id": None,
                "project_name": "Project Verify",
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
            "JOB-TEST-VERIFY",
            [{"relative_path": "A001_C001.braw", "size_bytes": 16, "metadata": {}, "has_backup": False}],
        )
        job_file = self.persistence.job_files.list_for_job("JOB-TEST-VERIFY")[0]
        self.persistence.job_files.update_copy_state(
            job_file_id=job_file.job_file_id,
            main_state="IN_PROGRESS",
        )
        self.persistence.job_files.update_verify_state(
            job_file_id=job_file.job_file_id,
            verify_main_state="IN_PROGRESS",
        )

        affected = self.persistence.job_files.mark_in_progress_as_failed(
            "JOB-TEST-VERIFY",
            "runtime_interrupted",
        )

        self.assertEqual(affected, 1)
        updated = self.persistence.job_files.list_for_job("JOB-TEST-VERIFY")[0]
        self.assertEqual(updated.copy_main_state, "FAILED")
        self.assertEqual(updated.verify_main_state, "FAILED")
        self.assertEqual(updated.error_code, "runtime_interrupted")
