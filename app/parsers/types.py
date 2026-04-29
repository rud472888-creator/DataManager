"""Parser data types and capability states."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class IntegrityState(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProbeResult:
    supported: bool
    confidence: float
    reason: str
    parser_name: str


@dataclass(frozen=True)
class ParserCapabilities:
    metadata: CapabilityState
    integrity: CapabilityState
    reason: str
    is_mock: bool = False

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "metadata": self.metadata.value,
            "integrity": self.integrity.value,
            "reason": self.reason,
            "is_mock": self.is_mock,
        }


@dataclass(frozen=True)
class ClipMetadata:
    format_name: str
    clip_name: str
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    is_mock: bool = False


@dataclass(frozen=True)
class IntegrityResult:
    state: IntegrityState
    reason: str
    is_mock: bool = False


@dataclass(frozen=True)
class CapabilityCheck:
    parser_name: str
    capabilities: ParserCapabilities
    sample_path: Path | None
    probe: ProbeResult | None = None
    metadata: ClipMetadata | None = None
    integrity: IntegrityResult | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "parser_name": self.parser_name,
            "capabilities": self.capabilities.as_dict(),
            "sample_path": str(self.sample_path) if self.sample_path else None,
            "probe": self.probe.__dict__ if self.probe else None,
            "metadata": self.metadata.__dict__ if self.metadata else None,
            "integrity": self.integrity.__dict__ if self.integrity else None,
        }
