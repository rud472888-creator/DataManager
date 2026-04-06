from __future__ import annotations

import os
from pathlib import Path

from app.persistence.repositories import VolumesRepository
from app.runtime.events import utc_now_iso


class VolumeMonitor:
    """Local-runtime-only volume detection shell.

    Sources are discovered from `/Volumes`. Destinations come from configured
    allowed destination roots. This is intentionally polling-oriented for A1.
    """

    def __init__(self, volumes_repository: VolumesRepository) -> None:
        self.volumes_repository = volumes_repository

    def refresh(self, allowed_destination_roots: tuple[str, ...]) -> list[dict[str, object]]:
        volumes: list[dict[str, object]] = []
        now = utc_now_iso()
        volumes_root = Path("/Volumes")
        if volumes_root.exists():
            for entry in sorted(volumes_root.iterdir()):
                if not entry.is_dir():
                    continue
                stat = os.statvfs(entry)
                record = {
                    "volume_id": f"source::{entry.resolve()}",
                    "display_name": entry.name,
                    "mount_path": str(entry.resolve()),
                    "volume_role": "source",
                    "is_removable": 1,
                    "filesystem_type": None,
                    "capacity_bytes": stat.f_blocks * stat.f_frsize,
                    "free_bytes": stat.f_bavail * stat.f_frsize,
                    "serial_hint": None,
                    "approval_state": "detected",
                    "last_seen_at": now,
                    "metadata_json": "{}",
                }
                self.volumes_repository.upsert_volume(record)
                volumes.append(record)

        for raw_root in allowed_destination_roots:
            entry = Path(raw_root).expanduser()
            entry.mkdir(parents=True, exist_ok=True)
            stat = os.statvfs(entry)
            record = {
                "volume_id": f"destination::{entry.resolve()}",
                "display_name": entry.name or str(entry.resolve()),
                "mount_path": str(entry.resolve()),
                "volume_role": "destination",
                "is_removable": 0,
                "filesystem_type": None,
                "capacity_bytes": stat.f_blocks * stat.f_frsize,
                "free_bytes": stat.f_bavail * stat.f_frsize,
                "serial_hint": None,
                "approval_state": "approved",
                "last_seen_at": now,
                "metadata_json": "{}",
            }
            self.volumes_repository.upsert_volume(record)
            volumes.append(record)
        return volumes
