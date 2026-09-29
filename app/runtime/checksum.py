"""Checksum helpers for runtime file verification."""

from __future__ import annotations

import hashlib
import os
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024, *, bypass_cache: bool = False) -> str:
    """Return the SHA-256 hex digest of ``path``.

    With ``bypass_cache`` the read is asked to skip the OS page cache so a freshly
    written replica is verified from the storage device, not from memory.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        if bypass_cache:
            _disable_read_cache(handle)
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_file(path: Path) -> None:
    """Flush a written file to stable storage (F_FULLFSYNC on macOS)."""

    fd = os.open(path, os.O_RDONLY)
    try:
        _full_fsync(fd)
        _drop_cached_pages(fd)
    finally:
        os.close(fd)


def fsync_directory(path: Path) -> None:
    """Best-effort flush of a directory entry change such as a rename."""

    with suppress(OSError):
        fd = os.open(path, os.O_RDONLY)
        try:
            _full_fsync(fd)
        finally:
            os.close(fd)


def _full_fsync(fd: int) -> None:
    full_fsync = getattr(fcntl, "F_FULLFSYNC", None)
    if full_fsync is not None:
        try:
            fcntl.fcntl(fd, full_fsync)
            return
        except OSError:
            pass
    os.fsync(fd)


def _disable_read_cache(handle: BinaryIO) -> None:
    fd = handle.fileno()
    no_cache = getattr(fcntl, "F_NOCACHE", None)
    if no_cache is not None:
        with suppress(OSError):
            fcntl.fcntl(fd, no_cache, 1)
    _drop_cached_pages(fd)


def _drop_cached_pages(fd: int) -> None:
    fadvise = getattr(os, "posix_fadvise", None)
    dont_need = getattr(os, "POSIX_FADV_DONTNEED", None)
    if fadvise is not None and dont_need is not None:
        with suppress(OSError):
            fadvise(fd, 0, 0, dont_need)
