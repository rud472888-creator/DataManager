"""Application configuration for the local runtime shell."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings sourced from environment variables."""

    host: str = "127.0.0.1"
    port: int = 8000
    token: str = "change-me"
    data_dir: Path = Path(".fdm_data")
    database_path: Path = Path(".fdm_data/fdm.sqlite3")
    dev_source_root: Path = Path(".fdm_fixtures/source")
    allowed_dest_roots: tuple[Path, ...] = (Path(".fdm_dest"),)
    log_level: str = "INFO"


def load_settings() -> Settings:
    """Load conservative local defaults without granting browser file authority."""

    roots = tuple(
        Path(item) for item in os.getenv("FDM_ALLOWED_DEST_ROOTS", ".fdm_dest").split(":") if item
    )
    return Settings(
        host=os.getenv("FDM_HOST", "127.0.0.1"),
        port=int(os.getenv("FDM_PORT", "8000")),
        token=os.getenv("FDM_TOKEN", "change-me"),
        data_dir=Path(os.getenv("FDM_DATA_DIR", ".fdm_data")),
        database_path=Path(os.getenv("FDM_DATABASE_PATH", ".fdm_data/fdm.sqlite3")),
        dev_source_root=Path(os.getenv("FDM_DEV_SOURCE_ROOT", ".fdm_fixtures/source")),
        allowed_dest_roots=roots or (Path(".fdm_dest"),),
        log_level=os.getenv("FDM_LOG_LEVEL", "INFO"),
    )
