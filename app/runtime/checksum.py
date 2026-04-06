from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from pathlib import Path


ChecksumProgressCallback = Callable[[int, float], Awaitable[None]]


class ChecksumMismatchError(RuntimeError):
    def __init__(self, *, path: Path, expected: str, actual: str) -> None:
        super().__init__(f"Checksum mismatch for {path}: expected {expected}, got {actual}")
        self.path = path
        self.expected = expected
        self.actual = actual


async def sha256_file(
    path: Path,
    *,
    chunk_size: int = 1024 * 1024,
    progress_callback: ChecksumProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    digest = hashlib.sha256()
    bytes_done = 0
    start = time.monotonic()
    with path.open("rb") as handle:
        while True:
            if cancel_check and cancel_check():
                raise asyncio.CancelledError
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            bytes_done += len(chunk)
            if progress_callback is not None:
                elapsed = max(time.monotonic() - start, 0.001)
                await progress_callback(bytes_done, elapsed)
            await asyncio.sleep(0)
    return digest.hexdigest()
