from __future__ import annotations

from pathlib import Path

from app.parsers.base import BaseParser
from app.parsers.types import ParserCapabilities, ProbeResult


class BrawParser(BaseParser):
    """BRAW-first parser contract shell for A1.

    Real metadata and frame extraction are intentionally stubbed.
    """

    def probe(self, file_path: Path) -> ProbeResult:
        supported = file_path.suffix.lower() == ".braw"
        return ProbeResult(
            supported=supported,
            confidence=1.0 if supported else 0.0,
            reason="A1 extension-based probe only",
        )

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(metadata=False, integrity=False, frame_capture=False)

    def parse_metadata(self, file_path: Path) -> dict[str, object]:
        raise NotImplementedError("BRAW metadata parsing is stubbed in A1")

    def check_integrity(self, file_path: Path) -> dict[str, object]:
        raise NotImplementedError("BRAW integrity checks are stubbed in A1")

    def capture_frames(self, file_path: Path, indices: list[int]) -> list[Path]:
        raise NotImplementedError("BRAW frame capture is stubbed in A1")

    def get_format_name(self) -> str:
        return "BRAW"

    def get_version(self) -> str:
        return "a1-stub"
