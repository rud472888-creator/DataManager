"""Runtime media format profiles for offload scanning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaFormatProfile:
    name: str
    suffixes: tuple[str, ...]


SUPPORTED_MEDIA_FORMATS = (
    MediaFormatProfile("BRAW", (".braw",)),
    MediaFormatProfile("R3D", (".r3d",)),
    MediaFormatProfile("ARRIRAW", (".ari", ".mxf")),
    MediaFormatProfile("STANDARD_VIDEO", (".mov", ".mp4")),
)

SUPPORTED_SUFFIXES = frozenset(
    suffix for profile in SUPPORTED_MEDIA_FORMATS for suffix in profile.suffixes
)


def supported_format_names() -> list[str]:
    return [profile.name for profile in SUPPORTED_MEDIA_FORMATS]


def supported_suffixes() -> list[str]:
    return sorted(SUPPORTED_SUFFIXES)


def format_name_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    for profile in SUPPORTED_MEDIA_FORMATS:
        if suffix in profile.suffixes:
            return profile.name
    return None
