from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProbeResult:
    supported: bool
    confidence: float
    reason: str


@dataclass(slots=True)
class ParserCapabilities:
    metadata: bool
    integrity: bool
    frame_capture: bool
