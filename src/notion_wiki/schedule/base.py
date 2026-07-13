"""Scheduler protocol — one implementation per OS, dispatched by `detect_scheduler()`
(docs/design.md §10). `service install` never asks the user to pick a mechanism."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ScheduleStatus:
    installed: bool
    detail: str = ""


class Scheduler(Protocol):
    name: str

    def install(self, interval_minutes: int) -> list[str]:
        """Register the repeating `notionwiki pull` schedule. Returns a list of
        advisory warning strings (empty if none) — e.g. Linux's headless
        Secret Service warning (§11)."""
        ...

    def uninstall(self) -> None: ...

    def status(self) -> ScheduleStatus: ...


def detect_scheduler() -> Scheduler:
    if sys.platform == "win32":
        from notion_wiki.schedule.windows import WindowsScheduler

        return WindowsScheduler()
    if sys.platform == "darwin":
        from notion_wiki.schedule.macos import MacScheduler

        return MacScheduler()
    from notion_wiki.schedule.linux import LinuxScheduler

    return LinuxScheduler()


def pull_argv() -> list[str]:
    """Argv for invoking `notionwiki pull` — prefer the installed console script,
    fall back to `python -m notion_wiki.cli` if it's not on PATH."""
    import shutil

    exe = shutil.which("notionwiki")
    if exe:
        return [exe, "pull"]
    return [sys.executable, "-m", "notion_wiki.cli", "pull"]
