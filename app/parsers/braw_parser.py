from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.parsers.base import BaseParser
from app.parsers.types import ClipMetadata, ParserCapabilities, ProbeResult


def _coerce_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pick(payload: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if "." in key:
            current: object = payload
            found = True
            for part in key.split("."):
                if not isinstance(current, dict) or part not in current:
                    found = False
                    break
                current = current[part]
            if found:
                return current
            continue
        if key in payload:
            return payload[key]
    return None


@dataclass(slots=True)
class BrawMetadataAdapter:
    command: tuple[str, ...] | None = None
    resolution_reason: str = "No BRAW metadata adapter configured"

    @classmethod
    def from_environment(cls) -> "BrawMetadataAdapter":
        raw = os.getenv("FDM_BRAW_METADATA_COMMAND", "").strip()
        if not raw:
            return cls()
        parts = shlex.split(raw)
        if not parts:
            return cls()
        resolved = shutil.which(parts[0])
        if resolved is None:
            return cls(command=None, resolution_reason=f"Configured command not found: {parts[0]}")
        return cls(command=(resolved, *parts[1:]), resolution_reason=f"Using configured adapter: {resolved}")

    def is_available(self) -> bool:
        return self.command is not None

    def describe(self) -> dict[str, object]:
        return {
            "available": self.is_available(),
            "reason": self.resolution_reason,
            "command": list(self.command) if self.command is not None else None,
        }

    def extract(self, file_path: Path) -> dict[str, Any]:
        if self.command is None:
            raise RuntimeError(self.resolution_reason)
        completed = subprocess.run(
            [*self.command, str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or "adapter returned non-zero exit status"
            raise RuntimeError(stderr)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("adapter output was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("adapter output must be a JSON object")
        return payload


class BrawParser(BaseParser):
    """BRAW-first parser with an honest capability-gated metadata adapter."""

    def __init__(self, adapter: BrawMetadataAdapter | None = None) -> None:
        self._adapter = adapter or BrawMetadataAdapter.from_environment()

    def probe(self, file_path: Path) -> ProbeResult:
        supported = file_path.suffix.lower() == ".braw"
        return ProbeResult(
            supported=supported,
            confidence=1.0 if supported else 0.0,
            reason="A1 extension-based probe only",
        )

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            metadata=self._adapter.is_available(),
            integrity=False,
            frame_capture=False,
        )

    def parse_metadata(self, file_path: Path) -> ClipMetadata:
        if not self.probe(file_path).supported:
            raise ValueError(f"Unsupported file type for BRAW parser: {file_path}")
        stat = file_path.stat()
        raw_payload: dict[str, Any] = {}
        parser_notes: list[str] = []
        metadata_status = "capability_gated"
        metadata_source = "filesystem_fallback"
        if self._adapter.is_available():
            raw_payload = self._adapter.extract(file_path)
            metadata_status = "parsed"
            metadata_source = "external_adapter"
            parser_notes.append("Metadata normalized from configured BRAW adapter output.")
        else:
            parser_notes.append(self._adapter.resolution_reason)

        modified_at = datetime.fromtimestamp(stat.st_mtime, UTC).replace(microsecond=0).isoformat()
        raw_metadata = {
            "metadata_status": metadata_status,
            "metadata_source": metadata_source,
            "parser_notes": parser_notes,
            "dependency": self._adapter.describe(),
            "file_name": file_path.name,
            "file_size_bytes": stat.st_size,
            "file_modified_at": modified_at,
            "detected_by_extension": True,
            "adapter_payload": raw_payload,
        }
        return ClipMetadata(
            clip_name=_coerce_str(_pick(raw_payload, "clip_name", "clipName")) or file_path.stem,
            reel_name=_coerce_str(_pick(raw_payload, "reel_name", "reelName")),
            camera_id=_coerce_str(_pick(raw_payload, "camera_id", "cameraId", "camera.id")),
            codec=_coerce_str(_pick(raw_payload, "codec", "video.codec")),
            resolution_width=_coerce_int(_pick(raw_payload, "resolution_width", "width", "video.width")),
            resolution_height=_coerce_int(_pick(raw_payload, "resolution_height", "height", "video.height")),
            fps=_coerce_float(_pick(raw_payload, "fps", "frame_rate", "video.fps")),
            duration_frames=_coerce_int(
                _pick(raw_payload, "duration_frames", "frame_count", "video.frame_count")
            ),
            timecode_start=_coerce_str(_pick(raw_payload, "timecode_start", "timecode", "video.timecode_start")),
            shot_date=_coerce_str(_pick(raw_payload, "shot_date", "capture_date", "record_date")),
            iso_value=_coerce_int(_pick(raw_payload, "iso_value", "iso", "camera.iso")),
            white_balance_kelvin=_coerce_int(
                _pick(raw_payload, "white_balance_kelvin", "white_balance", "camera.white_balance_kelvin")
            ),
            lens=self._normalize_lens(raw_payload),
            raw_metadata=raw_metadata,
        )

    def check_integrity(self, file_path: Path) -> dict[str, object]:
        raise NotImplementedError("BRAW integrity checks are stubbed in A1")

    def capture_frames(self, file_path: Path, indices: list[int]) -> list[Path]:
        raise NotImplementedError("BRAW frame capture is stubbed in A1")

    def get_format_name(self) -> str:
        return "BRAW"

    def get_version(self) -> str:
        return "a3-braw-metadata-adapter"

    @staticmethod
    def _normalize_lens(raw_payload: dict[str, Any]) -> dict[str, Any] | None:
        lens_payload = _pick(raw_payload, "lens")
        if isinstance(lens_payload, dict):
            return {str(key): value for key, value in lens_payload.items()}

        model = _coerce_str(_pick(raw_payload, "lens_model", "lensModel"))
        focal_length = _pick(raw_payload, "focal_length_mm", "focalLengthMm")
        aperture = _pick(raw_payload, "aperture_t_stop", "aperture", "lens_aperture")
        normalized = {
            key: value
            for key, value in {
                "model": model,
                "focal_length_mm": _coerce_float(focal_length),
                "aperture": _coerce_float(aperture),
            }.items()
            if value is not None
        }
        return normalized or None
