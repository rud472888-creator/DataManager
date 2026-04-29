"""Runtime-only parser protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.parsers.types import (
    CapturedFrame,
    ClipMetadata,
    IntegrityResult,
    ParserCapabilities,
    ProbeResult,
)


class Parser(Protocol):
    """Parser contract executed only by the local runtime."""

    def get_format_name(self) -> str:
        """Return the media format name."""

    def get_version(self) -> str:
        """Return the parser adapter version."""

    def capabilities(self) -> ParserCapabilities:
        """Return truthful parser capability status."""

    def probe(self, file_path: Path) -> ProbeResult:
        """Inspect a local runtime path."""

    def parse_metadata(self, file_path: Path) -> ClipMetadata:
        """Parse metadata from a local runtime path."""

    def check_integrity(self, file_path: Path) -> IntegrityResult:
        """Check media integrity from a local runtime path."""

    def capture_frames(
        self,
        file_path: Path,
        output_dir: Path,
        indices: list[int],
    ) -> list[CapturedFrame]:
        """Capture frames from a local runtime path."""
