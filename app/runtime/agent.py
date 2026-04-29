"""Local runtime agent foundation."""

from __future__ import annotations

from dataclasses import dataclass

from app import __version__
from app.api.schemas import RuntimeStatusPayload
from app.config import Settings
from app.parsers.registry import default_registry
from app.parsers.types import CapabilityState
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import VolumeRepository
from app.runtime.events import MemoryEventPublisher
from app.runtime.lifecycle import JobLifecycleService
from app.runtime.recovery import RecoveryLoader
from app.runtime.scheduler import SingleActiveJobScheduler
from app.runtime.volume_monitor import MockVolumeProvider, VolumeSnapshot


@dataclass
class RuntimeAgent:
    """Stage 3 local runtime foundation."""

    settings: Settings
    database: Database
    name: str = "Footage Data Manager Runtime"

    def __post_init__(self) -> None:
        self.events = MemoryEventPublisher()
        self.scheduler = SingleActiveJobScheduler()
        self.volume_provider = MockVolumeProvider(self.settings.allowed_dest_roots)
        self.lifecycle = JobLifecycleService(self.database)
        self.recovery = RecoveryLoader(self.lifecycle)

    def initialize(self) -> None:
        """Apply migrations and seed safe mock volume data."""

        with self.database.session() as connection:
            apply_migrations(connection)
            snapshot = self.volume_provider.scan()
            VolumeRepository(connection).upsert_many(snapshot.sources + snapshot.destinations)

    def status_message(self) -> str:
        return "local runtime foundation online"

    def status_payload(self) -> RuntimeStatusPayload:
        scheduler_status = self.scheduler.status()
        braw = default_registry().by_format("BRAW")
        braw_capabilities = braw.capabilities() if braw else None
        return {
            "runtime": "online",
            "version": __version__,
            "platform": "macOS",
            "active_job_id": scheduler_status.active_job_id,
            "capabilities": {
                "braw_metadata": (
                    braw_capabilities.metadata.value
                    if braw_capabilities
                    else CapabilityState.UNKNOWN.value
                ),
                "braw_frame_capture": (
                    braw_capabilities.frame_capture.value
                    if braw_capabilities
                    else CapabilityState.UNKNOWN.value
                ),
                "checksum": "available",
            },
            "messages": [
                self.status_message(),
                "Stage 3 foundation only; deep offload behavior starts in later sprints.",
            ],
        }

    def volume_snapshot(self) -> VolumeSnapshot:
        return self.volume_provider.scan()
