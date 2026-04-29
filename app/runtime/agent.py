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
from app.persistence.repositories import JobRepository, VolumeRepository
from app.runtime.events import MemoryEventPublisher
from app.runtime.lifecycle import JobLifecycleService
from app.runtime.media_formats import supported_format_names, supported_suffixes
from app.runtime.recovery import RecoveryLoader
from app.runtime.runner import RuntimeJobRunner
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
        self.volume_provider = MockVolumeProvider(
            self.settings.allowed_dest_roots,
            self.settings.dev_source_root,
        )
        self.lifecycle = JobLifecycleService(self.database)
        self.recovery = RecoveryLoader(self.lifecycle)
        self.runner = RuntimeJobRunner(
            database=self.database,
            lifecycle=self.lifecycle,
            volume_provider=self.volume_provider,
        )

    def initialize(self) -> None:
        """Apply migrations and seed safe mock volume data."""

        with self.database.session() as connection:
            apply_migrations(connection)
            snapshot = self.volume_provider.scan()
            VolumeRepository(connection).upsert_many(snapshot.sources + snapshot.destinations)

    def status_message(self) -> str:
        return "local runtime online"

    def status_payload(self) -> RuntimeStatusPayload:
        braw = default_registry().by_format("BRAW")
        r3d = default_registry().by_format("R3D")
        arriraw = default_registry().by_format("ARRIRAW")
        braw_capabilities = braw.capabilities() if braw else None
        r3d_capabilities = r3d.capabilities() if r3d else None
        arriraw_capabilities = arriraw.capabilities() if arriraw else None
        return {
            "runtime": "online",
            "version": __version__,
            "platform": "macOS",
            "active_job_id": self.active_job_id(),
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
                "r3d_metadata": (
                    r3d_capabilities.metadata.value
                    if r3d_capabilities
                    else CapabilityState.UNKNOWN.value
                ),
                "r3d_frame_capture": (
                    r3d_capabilities.frame_capture.value
                    if r3d_capabilities
                    else CapabilityState.UNKNOWN.value
                ),
                "arriraw_metadata": (
                    arriraw_capabilities.metadata.value
                    if arriraw_capabilities
                    else CapabilityState.UNKNOWN.value
                ),
                "arriraw_frame_capture": (
                    arriraw_capabilities.frame_capture.value
                    if arriraw_capabilities
                    else CapabilityState.UNKNOWN.value
                ),
                "checksum": "available",
                "supported_offload_formats": supported_format_names(),
                "supported_offload_suffixes": supported_suffixes(),
            },
            "messages": [
                self.status_message(),
                "Job requests run through the local runtime offload, parse, and report pipeline.",
            ],
        }

    def volume_snapshot(self) -> VolumeSnapshot:
        return self.volume_provider.scan()

    def active_job_id(self) -> str | None:
        with self.database.session() as connection:
            return JobRepository(connection).active_job_id()

    def run_job(self, job_id: str) -> None:
        self.runner.run(job_id)
