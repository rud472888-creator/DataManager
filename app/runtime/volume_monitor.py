"""Runtime-owned volume provider abstractions."""

from __future__ import annotations

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

    def __init__(self, allowed_dest_roots: tuple[Path, ...]) -> None:
        self.allowed_dest_roots = allowed_dest_roots

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
                    display_path="/Volumes/MockSource",
                    status="available",
                    bytes_available=1024 * 1024,
                )
            ],
            destinations=destinations,
        )
