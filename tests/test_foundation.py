import json
import sqlite3

from app.config import load_settings
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import EventRepository, JobRepository, SettingsRepository
from app.runtime.state_machine import CommandName, JobState, decide_command


def test_settings_loading_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("FDM_HOST", "0.0.0.0")
    monkeypatch.setenv("FDM_PORT", "9000")
    monkeypatch.setenv("FDM_DATABASE_PATH", ".tmp/test.sqlite3")
    monkeypatch.setenv("FDM_ALLOWED_DEST_ROOTS", "/Volumes/Main:/Volumes/Backup")

    settings = load_settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert str(settings.database_path) == ".tmp/test.sqlite3"
    assert [str(path) for path in settings.allowed_dest_roots] == [
        "/Volumes/Main",
        "/Volumes/Backup",
    ]


def test_database_migration_and_repository_lifecycle(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job()
        event = EventRepository(connection).append(
            "job_created",
            job_id=job.job_id,
            payload={"state": job.state},
        )
        SettingsRepository(connection).set_json("ui", {"density": "normal"})

    with database.session() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        setting = SettingsRepository(connection).get("ui")

    assert {
        "jobs",
        "job_events",
        "job_files",
        "clips",
        "reports",
        "system_volumes",
        "settings",
    } <= tables
    assert event.event_id.startswith("evt-")
    assert setting is not None
    assert json.loads(setting.value_json) == {"density": "normal"}


def test_database_session_rolls_back_on_error(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    try:
        with database.session() as connection:
            apply_migrations(connection)
            JobRepository(connection).create_stub_job()
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    with database.session() as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]

    assert count == 0


def test_state_enum_serialization_and_command_decisions() -> None:
    pause = decide_command(JobState.COPYING, CommandName.PAUSE)
    resume = decide_command(JobState.COPYING, CommandName.RESUME)

    assert str(JobState.COPYING) == "COPYING"
    assert pause.accepted is True
    assert resume.accepted is False
    assert "not allowed" in resume.reason


def test_schema_enforces_foreign_keys(tmp_path) -> None:
    database = Database(tmp_path / "fdm.sqlite3")

    with database.session() as connection:
        apply_migrations(connection)
        try:
            connection.execute(
                """
                INSERT INTO job_files (file_id, job_id, source_relpath, size_bytes, status)
                VALUES ('file-1', 'missing-job', 'A001_C001.braw', 10, 'pending')
                """
            )
        except sqlite3.IntegrityError:
            rejected = True
        else:
            rejected = False

    assert rejected is True
