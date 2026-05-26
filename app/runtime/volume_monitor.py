"""Runtime-owned volume provider abstractions."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.persistence.models import SystemVolume


@dataclass(frozen=True)
class VolumeSnapshot:
    sources: list[SystemVolume]
    destinations: list[SystemVolume]


class VolumeProvider(Protocol):
    """Provider that runs inside the local runtime, never in the browser."""

    def scan(self) -> VolumeSnapshot:
        """Return runtime-discovered source and destination candidates."""


class MockVolumeProvider:
    """Safe mock provider for foundation tests and shell UI."""

    def __init__(self, allowed_dest_roots: tuple[Path, ...], source_root: Path) -> None:
        self.allowed_dest_roots = allowed_dest_roots
        self.source_root = source_root

    def scan(self) -> VolumeSnapshot:
        destinations = [
            SystemVolume(
                volume_id=f"dest-{index}",
                label=f"Destination {index + 1}",
                kind="destination",
                display_path=str(path),
                status="available",
                bytes_available=None,
            )
            for index, path in enumerate(self.allowed_dest_roots)
        ]
        return VolumeSnapshot(
            sources=[
                SystemVolume(
                    volume_id="mock-source",
                    label="Mock Source",
                    kind="source",
                    display_path=str(self.source_root),
                    status="available",
                    bytes_available=1024 * 1024,
                )
            ],
            destinations=destinations,
        )


class MacOSVolumeProvider:
    """Discover mounted macOS volumes and runtime-allowed destination roots."""

    def __init__(
        self,
        volume_scan_root: Path = Path("/Volumes"),
        allowed_dest_roots: tuple[Path, ...] = (),
        extra_source_roots: tuple[Path, ...] = (),
    ) -> None:
        self.volume_scan_root = volume_scan_root
        self.allowed_dest_roots = allowed_dest_roots
        self.extra_source_roots = extra_source_roots

    def scan(self) -> VolumeSnapshot:
        volume_paths = self._mounted_volume_paths()
        sources = [
            _volume(path, "source", f"src-{_slug(path.name)}") for path in volume_paths
        ]
        seen_sources = {_identity(path) for path in volume_paths}
        for index, root in enumerate(self.extra_source_roots):
            identity = _identity(root)
            if identity in seen_sources or not root.exists():
                continue
            seen_sources.add(identity)
            sources.append(_volume(root, "source", f"src-{_slug(root.name) or index}"))
        destinations = [
            _volume(path, "destination", f"dest-{_slug(path.name)}") for path in volume_paths
        ]

        seen_destinations = {_identity(path) for path in volume_paths}
        for index, root in enumerate(self.allowed_dest_roots):
            identity = _identity(root)
            if identity in seen_destinations:
                continue
            seen_destinations.add(identity)
            destinations.append(
                _volume(root, "destination", f"dest-{_slug(root.name) or index}")
            )
        return VolumeSnapshot(sources=sources, destinations=destinations)

    def _mounted_volume_paths(self) -> list[Path]:
        if not self.volume_scan_root.exists():
            return []
        paths: list[Path] = []
        for child in sorted(self.volume_scan_root.iterdir(), key=lambda path: path.name.lower()):
            if child.is_dir() and not _is_excluded_volume(child):
                paths.append(child)
        return paths


def _volume(path: Path, kind: str, volume_id: str) -> SystemVolume:
    return SystemVolume(
        volume_id=volume_id,
        label=path.name,
        kind=kind,
        display_path=str(path),
        status=_status(path),
        bytes_available=_bytes_available(path),
    )


def _status(path: Path) -> str:
    if not path.exists():
        return "missing"
    if not path.is_dir():
        return "missing"
    if not path.is_absolute():
        path = path.resolve()
    return "available" if path.exists() and _is_writable(path) else "read-only"


def _bytes_available(path: Path) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def _is_writable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def _is_excluded_volume(path: Path) -> bool:
    name = path.name
    normalized = name.lower().replace(" ", "")
    return name.startswith(".") or normalized in {"macintoshhd"} or "timemachine" in normalized


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "volume"


def _identity(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)
