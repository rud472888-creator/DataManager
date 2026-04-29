"""Source scanning for supported runtime-managed media files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.runtime.media_formats import SUPPORTED_SUFFIXES

EXCLUDED_NAMES = frozenset({".DS_Store"})


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    relpath: Path
    size_bytes: int


def is_excluded(path: Path) -> bool:
    return path.name in EXCLUDED_NAMES or path.name.startswith("._")


def is_supported(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES and not is_excluded(path)


def scan_source(source_root: Path) -> list[ScannedFile]:
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"source root is unavailable: {source_root}")
    files: list[ScannedFile] = []
    for path in sorted(source_root.rglob("*")):
        if is_excluded(path):
            continue
        if is_supported(path):
            files.append(
                ScannedFile(
                    path=path,
                    relpath=path.relative_to(source_root),
                    size_bytes=path.stat().st_size,
                )
            )
    return files
