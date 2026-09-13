# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Portable inter-process file locking for operational journals."""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Callable

__all__ = ["FileLockTimeoutError", "InterProcessFileLock"]


class FileLockTimeoutError(TimeoutError):
    """Raised when an operational journal lock cannot be acquired."""


class InterProcessFileLock:
    """Advisory exclusive lock with bounded waiting on POSIX and Windows."""

    def __init__(
        self,
        path: Path | str,
        *,
        timeout_seconds: float = 5.0,
        poll_seconds: float = 0.025,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds cannot be negative")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self._monotonic = monotonic
        self._handle: BinaryIO | None = None

    def _try_lock(self, handle: BinaryIO) -> bool:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return False
            return True

        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def acquire(self) -> "InterProcessFileLock":
        if self._handle is not None:
            raise RuntimeError("file lock is already acquired")
        handle = self.path.open("a+b")
        deadline = self._monotonic() + self.timeout_seconds
        while True:
            if self._try_lock(handle):
                self._handle = handle
                return self
            if self._monotonic() >= deadline:
                handle.close()
                raise FileLockTimeoutError(
                    f"timed out acquiring file lock: {self.path}"
                )
            time.sleep(self.poll_seconds)

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle = None
            handle.close()

    def __enter__(self) -> "InterProcessFileLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
