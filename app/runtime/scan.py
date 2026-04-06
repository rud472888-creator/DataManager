from __future__ import annotations

from pathlib import Path


EXCLUDED_NAMES = {".DS_Store"}
EXCLUDED_PREFIXES = ("._",)


def should_exclude(path: Path) -> bool:
    name = path.name
    if name in EXCLUDED_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def scan_source_volume(source_root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        if should_exclude(path):
            continue
        files.append(
            {
                "relative_path": str(path.relative_to(source_root)),
                "size_bytes": path.stat().st_size,
                "metadata": {},
            }
        )
    return files
