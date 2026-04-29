"""Runtime frame capture integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.parsers.base import Parser
from app.parsers.braw_parser import BrawUnavailableError
from app.parsers.types import CapturedFrame


@dataclass(frozen=True)
class CaptureResult:
    frames: list[CapturedFrame] = field(default_factory=list)
    unavailable_reason: str | None = None


class CaptureService:
    """Capture frames through a runtime parser without faking unavailable output."""

    def __init__(self, parser: Parser) -> None:
        self.parser = parser

    def capture_for_file(
        self,
        file_path: Path,
        output_dir: Path,
        indices: list[int],
    ) -> CaptureResult:
        try:
            frames = self.parser.capture_frames(file_path, output_dir, indices)
        except (BrawUnavailableError, OSError) as exc:
            return CaptureResult(unavailable_reason=str(exc))
        return CaptureResult(frames=frames)
