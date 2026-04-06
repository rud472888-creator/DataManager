from __future__ import annotations

from pathlib import Path

from app.persistence.db import Database


SCHEMA_VERSION = 2


def apply_migrations(database: Database, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    with database.connect() as connection:
        connection.executescript(sql)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
