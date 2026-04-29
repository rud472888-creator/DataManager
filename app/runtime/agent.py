"""Local runtime agent foundation."""

from __future__ import annotations

from dataclasses import dataclass

from app import __version__
from app.api.schemas import RuntimeStatusPayload
from app.config import Settings
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
        return {
            "runtime": "online",
            "version": __version__,
            "platform": "macOS",
            "active_job_id": self.active_job_id(),
            "capabilities": {
                "checksum": "available",
                "supported_offload_formats": supported_format_names(),
                "supported_offload_suffixes": supported_suffixes(),
            },
            "messages": [
                self.status_message(),
                "Job requests run through the local runtime clone, checksum, and report pipeline.",
            ],
        }

    def volume_snapshot(self) -> VolumeSnapshot:
        return self.volume_provider.scan()

    def active_job_id(self) -> str | None:
        with self.database.session() as connection:
            return JobRepository(connection).active_job_id()

    def run_job(self, job_id: str) -> None:
        self.runner.run(job_id)
