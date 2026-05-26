"""Standard MOV/MP4 parser backed by ffprobe."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.parsers.errors import ParserUnavailableError
from app.parsers.types import (
    CapabilityState,
    ClipMetadata,
    IntegrityResult,
    IntegrityState,
    ParserCapabilities,
    ProbeResult,
)


class StandardVideoParser:
    """Read basic MOV/MP4 metadata through ffprobe."""

    suffixes = (".mov", ".mp4")

    def __init__(self, ffprobe_command: str | None = None) -> None:
        self.ffprobe_command = ffprobe_command

    @classmethod
    def from_environment(cls) -> StandardVideoParser:
        return cls(os.getenv("FDM_FFPROBE_COMMAND") or "ffprobe")

    def get_format_name(self) -> str:
        return "STANDARD_VIDEO"

    def get_version(self) -> str:
        return "ffprobe-standard-video-0.1"

    def capabilities(self) -> ParserCapabilities:
        if self._resolved_command() is None:
            return ParserCapabilities(
                metadata=CapabilityState.UNAVAILABLE,
                integrity=CapabilityState.UNAVAILABLE,
                reason="ffprobe command is not configured or available",
            )
        return ParserCapabilities(
            metadata=CapabilityState.AVAILABLE,
            integrity=CapabilityState.PARTIAL,
            reason="ffprobe command available",
        )

    def probe(self, file_path: Path) -> ProbeResult:
        supported = file_path.suffix.lower() in self.suffixes
        return ProbeResult(
            supported=supported,
            confidence=0.8 if supported else 0.0,
            reason="extension matches standard video" if supported else "file extension is not .mov or .mp4",
            parser_name=self.get_format_name(),
        )

    def parse_metadata(self, file_path: Path) -> ClipMetadata:
        if file_path.suffix.lower() not in self.suffixes:
            raise ParserUnavailableError("file extension is not .mov or .mp4")
        payload = self._run_ffprobe(file_path)
        metadata = _metadata_from_payload(payload)
        return ClipMetadata(
            format_name=self.get_format_name(),
            clip_name=file_path.stem,
            metadata=metadata,
            is_mock=False,
        )

    def check_integrity(self, file_path: Path) -> IntegrityResult:
        if self._resolved_command() is None:
            return IntegrityResult(
                state=IntegrityState.UNKNOWN,
                reason="ffprobe command is not configured or available",
            )
        if not file_path.exists():
            return IntegrityResult(state=IntegrityState.FAILED, reason="sample file missing")
        try:
            self._run_ffprobe(file_path)
        except ParserUnavailableError as exc:
            return IntegrityResult(state=IntegrityState.FAILED, reason=str(exc))
        return IntegrityResult(state=IntegrityState.OK, reason="ffprobe metadata read")

    def _run_ffprobe(self, file_path: Path) -> dict[str, Any]:
        command = self._resolved_command()
        if command is None:
            raise ParserUnavailableError("ffprobe command is not configured or available")
        if not file_path.exists():
            raise ParserUnavailableError(f"standard video sample does not exist: {file_path}")
        result = subprocess.run(
            [
                command,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(file_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            reason = result.stderr.strip() or f"command exited {result.returncode}"
            raise ParserUnavailableError(f"ffprobe metadata command failed: {reason}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ParserUnavailableError("ffprobe metadata command did not return JSON") from exc
        if not isinstance(payload, dict):
            raise ParserUnavailableError("ffprobe metadata JSON must be an object")
        return payload

    def _resolved_command(self) -> str | None:
        if self.ffprobe_command is None:
            return None
        command = self.ffprobe_command
        if "/" in command:
            path = Path(command)
            return str(path) if path.exists() else None
        return shutil.which(command)


def _metadata_from_payload(payload: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ParserUnavailableError("ffprobe metadata JSON did not include streams")
    video_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ParserUnavailableError("ffprobe metadata JSON did not include a video stream")
    format_payload = payload.get("format") if isinstance(payload.get("format"), dict) else {}

    metadata: dict[str, str | int | float | bool | None] = {}
    _set(metadata, "container_format", format_payload.get("format_name"))
    _set(metadata, "video_codec", video_stream.get("codec_name"))
    _set(metadata, "width", _as_int(video_stream.get("width")))
    _set(metadata, "height", _as_int(video_stream.get("height")))
    _set(metadata, "fps", _frame_rate(video_stream))
    _set(metadata, "duration_seconds", _first_float(video_stream.get("duration"), format_payload.get("duration")))
    _set(metadata, "size_bytes", _as_int(format_payload.get("size")))
    _set(metadata, "bit_rate", _first_int(video_stream.get("bit_rate"), format_payload.get("bit_rate")))
    _set(metadata, "timecode", _first_str(_tag(video_stream, "timecode"), _tag(format_payload, "timecode")))
    return metadata


def _set(
    metadata: dict[str, str | int | float | bool | None],
    key: str,
    value: str | int | float | bool | None,
) -> None:
    if value is not None:
        metadata[key] = value


def _tag(payload: dict[str, Any], key: str) -> object:
    tags = payload.get("tags")
    if not isinstance(tags, dict):
        return None
    return tags.get(key)


def _frame_rate(video_stream: dict[str, Any]) -> float | None:
    for key in ("r_frame_rate", "avg_frame_rate"):
        parsed = _fraction(video_stream.get(key))
        if parsed is not None:
            return parsed
    return None


def _fraction(value: object) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return _as_float(value)
    numerator, denominator = value.split("/", maxsplit=1)
    num = _as_float(numerator)
    den = _as_float(denominator)
    if num is None or den in (None, 0):
        return None
    return num / den


def _first_float(*values: object) -> float | None:
    for value in values:
        parsed = _as_float(value)
        if parsed is not None:
            return parsed
    return None


def _first_int(*values: object) -> int | None:
    for value in values:
        parsed = _as_int(value)
        if parsed is not None:
            return parsed
    return None


def _first_str(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
