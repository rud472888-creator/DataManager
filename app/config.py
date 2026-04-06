from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    token: str
    data_dir: Path
    db_path: Path
    logs_dir: Path
    reports_dir: Path
    temp_dir: Path
    allowed_destination_roots: tuple[str, ...]
    log_level: str
    app_name: str = "Footage Data Manager"
    app_version: str = "0.2.0-a2"

    @classmethod
    def load(cls) -> "Settings":
        root = Path(
            os.environ.get("FDM_DATA_DIR", str(Path.cwd() / ".fdm_data"))
        ).expanduser()
        allowed_roots = tuple(_split_csv(os.environ.get("FDM_ALLOWED_DEST_ROOTS", "")))
        return cls(
            host=os.environ.get("FDM_HOST", "127.0.0.1"),
            port=int(os.environ.get("FDM_PORT", "4482")),
            token=os.environ.get("FDM_TOKEN", "change-me"),
            data_dir=root,
            db_path=root / "fdm.sqlite3",
            logs_dir=root / "logs",
            reports_dir=root / "reports",
            temp_dir=root / "tmp",
            allowed_destination_roots=allowed_roots,
            log_level=os.environ.get("FDM_LOG_LEVEL", "INFO"),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
