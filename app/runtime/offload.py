from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Awaitable, Callable


ProgressCallback = Callable[[int, float], Awaitable[None]]
PARTIAL_SUFFIX = ".fdm-partial"


def partial_copy_path(destination_path: Path) -> Path:
    return destination_path.with_name(destination_path.name + PARTIAL_SUFFIX)


def build_project_tree(destination_root: Path, project_name: str, source_label: str) -> dict[str, Path]:
    project_root = destination_root / project_name
    master_root = project_root / "00_master"
    reports_root = master_root / "reports"
    manifests_root = master_root / "manifests"
    logs_root = master_root / "logs"
    footage_root = project_root / "01_footage" / source_label
    for directory in (project_root, master_root, reports_root, manifests_root, logs_root, footage_root):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "project_root": project_root,
        "reports_root": reports_root,
        "manifests_root": manifests_root,
        "logs_root": logs_root,
        "footage_root": footage_root,
    }


async def copy_file_with_progress(
    *,
    source_path: Path,
    destination_path: Path,
    progress_callback: ProgressCallback,
    chunk_size: int = 1024 * 1024,
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = partial_copy_path(destination_path)
    if temp_path.exists():
        temp_path.unlink()
    bytes_done = 0
    start = time.monotonic()
    try:
        with source_path.open("rb") as src, temp_path.open("wb") as dst:
            while True:
                if cancel_check and cancel_check():
                    raise asyncio.CancelledError
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)
                bytes_done += len(chunk)
                elapsed = max(time.monotonic() - start, 0.001)
                await progress_callback(bytes_done, elapsed)
                await asyncio.sleep(0)
        shutil.copystat(source_path, temp_path, follow_symlinks=True)
        temp_path.replace(destination_path)
    except BaseException:
        if temp_path.exists():
            temp_path.unlink()
        raise
