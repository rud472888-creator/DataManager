"""Truthful unavailable parser adapters for future formats."""

from __future__ import annotations

from pathlib import Path

from app.parsers.errors import ParserUnavailableError
from app.parsers.types import (
    CapabilityState,
    ClipMetadata,
    IntegrityResult,
    IntegrityState,
    ParserCapabilities,
    ProbeResult,
)


class UnavailableFormatParser:
    """Parser boundary for offload-supported formats without SDK integration."""

    def __init__(self, *, format_name: str, suffixes: tuple[str, ...], reason: str) -> None:
        self.format_name = format_name
        self.suffixes = suffixes
        self.reason = reason

    def get_format_name(self) -> str:
        return self.format_name

    def get_version(self) -> str:
        return "unavailable-adapter-0.1"

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            metadata=CapabilityState.UNAVAILABLE,
            integrity=CapabilityState.UNAVAILABLE,
            reason=self.reason,
        )

    def probe(self, file_path: Path) -> ProbeResult:
        supported = file_path.suffix.lower() in self.suffixes
        return ProbeResult(
            supported=supported,
            confidence=0.5 if supported else 0.0,
            reason=(
                f"extension matches {self.format_name}; SDK adapter is not configured"
                if supported
                else f"file extension is not supported by {self.format_name}"
            ),
            parser_name=self.get_format_name(),
        )

    def parse_metadata(self, file_path: Path) -> ClipMetadata:
        raise ParserUnavailableError(self.reason)

    def check_integrity(self, file_path: Path) -> IntegrityResult:
        return IntegrityResult(state=IntegrityState.UNKNOWN, reason=self.reason)


def r3d_unavailable_parser() -> UnavailableFormatParser:
    return UnavailableFormatParser(
        format_name="R3D",
        suffixes=(".r3d",),
        reason="R3D SDK command is not configured",
    )


def arriraw_unavailable_parser() -> UnavailableFormatParser:
    return UnavailableFormatParser(
        format_name="ARRIRAW",
        suffixes=(".ari", ".mxf"),
        reason="ARRIRAW SDK command is not configured",
    )
