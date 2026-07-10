"""Cross-platform single-instance lock for the pull loop (docs/design.md §5.1).

A manual `notion-wiki pull` can overlap a scheduled tick, and a slow run
(large workspace, 429 backoff) can exceed the ~60s cadence and overlap the
next scheduled tick too. Two writers to state.db and raw/*.md is a
corruption path, so every run takes this lock before doing anything else;
a run that can't acquire it exits immediately (logged as `skipped`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO


class LockAcquisitionError(RuntimeError):
    """Raised when another notion-wiki pull already holds the lock."""


class SingleInstanceLock:
    def __init__(self, path: Path):
        self._path = path
        self._fh: IO[bytes] | None = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self._path, "a+b")
        fh.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise LockAcquisitionError(
                f"another notion-wiki pull already holds the lock at {self._path}"
            ) from exc
        self._fh = fh

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> SingleInstanceLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
