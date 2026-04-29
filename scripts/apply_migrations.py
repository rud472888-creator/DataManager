#!/usr/bin/env python3
"""Apply SQLite migrations for the local runtime foundation."""

from __future__ import annotations

from app.config import load_settings
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations


def main() -> None:
    settings = load_settings()
    with Database(settings.database_path).session() as connection:
        apply_migrations(connection)
    print(f"Applied migrations to {settings.database_path}")


if __name__ == "__main__":
    main()
