"""SQLite connection and session helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect_database(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection owned by the local runtime."""

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class Database:
    """Small SQLite session factory for the local runtime."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection and commit or roll back the transaction."""

        connection = connect_database(self.path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
