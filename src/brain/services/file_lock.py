"""Cross-platform advisory file locking for ingestion worker and maintenance scripts."""
from __future__ import annotations

import os
import sys
from typing import IO

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None


def acquire_exclusive_lock(handle: IO) -> None:
    """Acquires a non-blocking exclusive lock on handle, raising BlockingIOError if unavailable."""
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif msvcrt is not None:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except (OSError, IOError) as exc:
            raise BlockingIOError("File is locked by another process") from exc
    else:
        pass


def release_exclusive_lock(handle: IO) -> None:
    """Releases the lock on handle."""
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError):
            pass
    elif msvcrt is not None:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except (OSError, IOError):
            pass
