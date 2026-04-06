from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(slots=True)
class ClipMetadata:
    clip_name: str | None = None
    reel_name: str | None = None
    camera_id: str | None = None
    codec: str | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None
    fps: float | None = None
    duration_frames: int | None = None
    timecode_start: str | None = None
    shot_date: str | None = None
    iso_value: int | None = None
    white_balance_kelvin: int | None = None
    lens: dict[str, Any] | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def as_clip_row(self) -> dict[str, Any]:
        return {
            "clip_name": self.clip_name,
            "reel_name": self.reel_name,
            "camera_id": self.camera_id,
            "codec": self.codec,
            "resolution_width": self.resolution_width,
            "resolution_height": self.resolution_height,
            "fps": self.fps,
            "duration_frames": self.duration_frames,
            "timecode_start": self.timecode_start,
            "shot_date": self.shot_date,
            "iso_value": self.iso_value,
            "white_balance_kelvin": self.white_balance_kelvin,
            "lens": self.lens,
        }

    def as_safe_payload(self) -> dict[str, Any]:
        payload = self.as_clip_row()
        payload.update(
            {
                "metadata_status": self.raw_metadata.get("metadata_status", "unknown"),
                "metadata_source": self.raw_metadata.get("metadata_source", "unknown"),
                "parser_notes": list(self.raw_metadata.get("parser_notes", [])),
            }
        )
        return payload
