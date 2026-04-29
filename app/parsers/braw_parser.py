"""BRAW parser adapters and truthful capability gate."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from app.parsers.errors import ParserUnavailableError
from app.parsers.types import (
    CapabilityCheck,
    CapabilityState,
    ClipMetadata,
    IntegrityResult,
    IntegrityState,
    ParserCapabilities,
    ProbeResult,
)


class BrawUnavailableError(ParserUnavailableError):
    """Raised when real BRAW behavior is requested but unavailable."""


class BrawAdapter:
    """Real BRAW adapter boundary.

    The command contract is intentionally narrow: when configured, the metadata
    command receives a sample path and must print JSON. Frame capture is outside
    this clone app and belongs to the separate capture tool.
    """

    def __init__(self, metadata_command: str | None = None) -> None:
        self.metadata_command = metadata_command

    @classmethod
    def from_environment(cls) -> BrawAdapter:
        return cls(metadata_command=os.getenv("FDM_BRAW_METADATA_COMMAND") or None)

    def get_format_name(self) -> str:
        return "BRAW"

    def get_version(self) -> str:
        return "real-adapter-boundary-0.1"

    def capabilities(self) -> ParserCapabilities:
        if self.metadata_command is None:
            return ParserCapabilities(
                metadata=CapabilityState.UNAVAILABLE,
                integrity=CapabilityState.UNAVAILABLE,
                reason="BRAW SDK command is not configured",
            )
        return ParserCapabilities(
            metadata=CapabilityState.PARTIAL,
            integrity=CapabilityState.UNAVAILABLE,
            reason="BRAW metadata command configured; sample validation required",
        )

    def probe(self, file_path: Path) -> ProbeResult:
        if file_path.suffix.lower() != ".braw":
            return ProbeResult(
                supported=False,
                confidence=0.0,
                reason="file extension is not .braw",
                parser_name=self.get_format_name(),
            )
        return ProbeResult(
            supported=True,
            confidence=0.6,
            reason="extension matches BRAW; SDK validation still required",
            parser_name=self.get_format_name(),
        )

    def parse_metadata(self, file_path: Path) -> ClipMetadata:
        if self.metadata_command is None:
            raise BrawUnavailableError("BRAW SDK command is not configured")
        if not file_path.exists():
            raise BrawUnavailableError(f"BRAW sample does not exist: {file_path}")
        result = subprocess.run(
            [self.metadata_command, str(file_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            reason = result.stderr.strip() or f"command exited {result.returncode}"
            raise BrawUnavailableError(f"BRAW metadata command failed: {reason}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise BrawUnavailableError("BRAW metadata command did not return JSON") from exc
        return ClipMetadata(
            format_name="BRAW",
            clip_name=file_path.stem,
            metadata=_string_key_payload(payload),
            is_mock=False,
        )

    def check_integrity(self, file_path: Path) -> IntegrityResult:
        if self.metadata_command is None:
            return IntegrityResult(
                state=IntegrityState.UNKNOWN,
                reason="BRAW SDK command is not configured",
            )
        if not file_path.exists():
            return IntegrityResult(state=IntegrityState.FAILED, reason="sample file missing")
        return IntegrityResult(
            state=IntegrityState.UNKNOWN,
            reason="integrity command is not implemented in Sprint 0",
        )

    def check_capability(self, sample_path: Path | None = None) -> CapabilityCheck:
        capabilities = self.capabilities()
        probe = self.probe(sample_path) if sample_path else None
        metadata: ClipMetadata | None = None
        integrity: IntegrityResult | None = None
        if sample_path and capabilities.metadata is not CapabilityState.UNAVAILABLE:
            try:
                metadata = self.parse_metadata(sample_path)
                integrity = self.check_integrity(sample_path)
                capabilities = ParserCapabilities(
                    metadata=CapabilityState.AVAILABLE,
                    integrity=CapabilityState.PARTIAL,
                    reason="metadata command succeeded",
                )
            except BrawUnavailableError as exc:
                capabilities = ParserCapabilities(
                    metadata=CapabilityState.UNAVAILABLE,
                    integrity=CapabilityState.UNAVAILABLE,
                    reason=str(exc),
                )
        return CapabilityCheck(
            parser_name=self.get_format_name(),
            capabilities=capabilities,
            sample_path=sample_path,
            probe=probe,
            metadata=metadata,
            integrity=integrity,
        )


class MockBrawParser:
    """Deterministic mock parser for tests only."""

    def get_format_name(self) -> str:
        return "BRAW_MOCK"

    def get_version(self) -> str:
        return "mock-0.1"

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            metadata=CapabilityState.AVAILABLE,
            integrity=CapabilityState.AVAILABLE,
            reason="mock parser for tests only",
            is_mock=True,
        )

    def probe(self, file_path: Path) -> ProbeResult:
        return ProbeResult(
            supported=file_path.suffix.lower() == ".braw",
            confidence=1.0 if file_path.suffix.lower() == ".braw" else 0.0,
            reason="mock extension check",
            parser_name=self.get_format_name(),
        )

    def parse_metadata(self, file_path: Path) -> ClipMetadata:
        return ClipMetadata(
            format_name="BRAW",
            clip_name=file_path.stem,
            metadata={
                "mock": True,
                "camera": "Mock Camera",
                "reel": "A001",
                "fps": 24.0,
            },
            is_mock=True,
        )

    def check_integrity(self, file_path: Path) -> IntegrityResult:
        return IntegrityResult(
            state=IntegrityState.OK,
            reason="mock integrity ok",
            is_mock=True,
        )


def _string_key_payload(payload: object) -> dict[str, str | int | float | bool | None]:
    if not isinstance(payload, dict):
        raise BrawUnavailableError("BRAW metadata JSON must be an object")
    clean: dict[str, str | int | float | bool | None] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, str | int | float | bool | type(None)):
            clean[key] = value
    return clean
