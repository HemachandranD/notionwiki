from pathlib import Path

import pytest

from notion_wiki.store.lock import LockAcquisitionError, SingleInstanceLock


def test_acquire_and_release(tmp_path: Path):
    lock = SingleInstanceLock(tmp_path / "pull.lock")
    lock.acquire()
    lock.release()


def test_second_acquire_fails_while_held(tmp_path: Path):
    lock_path = tmp_path / "pull.lock"
    first = SingleInstanceLock(lock_path)
    first.acquire()
    try:
        second = SingleInstanceLock(lock_path)
        with pytest.raises(LockAcquisitionError):
            second.acquire()
    finally:
        first.release()


def test_lock_available_again_after_release(tmp_path: Path):
    lock_path = tmp_path / "pull.lock"
    first = SingleInstanceLock(lock_path)
    first.acquire()
    first.release()

    second = SingleInstanceLock(lock_path)
    second.acquire()
    second.release()


def test_context_manager(tmp_path: Path):
    lock_path = tmp_path / "pull.lock"
    with SingleInstanceLock(lock_path):
        with pytest.raises(LockAcquisitionError):
            SingleInstanceLock(lock_path).acquire()
