"""Small migration runner for the Stage 3 SQLite foundation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

REQUIRED_COLUMNS: dict[str, set[str]] = {
    "jobs": {
        "job_id",
        "project_name",
        "source_path_ids_json",
        "replica_path_ids_json",
        "state",
        "current_step",
        "stats_json",
        "policy_json",
        "operator_origin",
        "recovery_cursor_json",
    },
    "job_events": {
        "event_id",
        "job_id",
        "event_type",
        "state_before",
        "state_after",
        "command",
        "accepted",
        "reason",
        "payload_json",
        "operator_origin",
    },
    "job_files": {
        "file_id",
        "job_id",
        "source_path_id",
        "source_relpath",
        "size_bytes",
        "status",
    },
    "job_file_replicas": {
        "file_id",
        "path_id",
        "dest_relpath",
        "checksum",
        "status",
    },
    "clips": {"clip_id", "job_id", "file_id", "format_name", "parser_version"},
    "reports": {"report_id", "job_id", "report_type", "artifact_relpath", "status"},
    "system_volumes": {"volume_id", "label", "kind", "display_path", "status"},
    "settings": {"key", "value_json"},
}


def schema_path() -> Path:
    """Return the packaged bootstrap schema path."""

    return Path(__file__).with_name("schema.sql")


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply the checked-in schema idempotently."""

    _archive_incompatible_tables(connection)
    connection.executescript(schema_path().read_text())
    connection.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")


def _archive_incompatible_tables(connection: sqlite3.Connection) -> None:
    for table, required_columns in REQUIRED_COLUMNS.items():
        existing_columns = _table_columns(connection, table)
        if existing_columns and not required_columns <= existing_columns:
            archive_name = _archive_name(connection, table)
            connection.execute(f"ALTER TABLE {table} RENAME TO {archive_name}")


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _archive_name(connection: sqlite3.Connection, table: str) -> str:
    index = 1
    while True:
        candidate = f"{table}_legacy_{index}"
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (candidate,),
        ).fetchone()
        if exists is None:
            return candidate
        index += 1
