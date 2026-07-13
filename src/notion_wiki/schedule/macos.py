"""macOS launchd integration (docs/design.md §10): a user LaunchAgent with
`StartInterval` (seconds) running `notionwiki pull`."""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

from notion_wiki.schedule.base import ScheduleStatus, pull_argv

LABEL = "com.notionwiki.pull"


def _launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _plist_path() -> Path:
    return _launch_agents_dir() / f"{LABEL}.plist"


class MacScheduler:
    name = "macos"

    def install(self, interval_minutes: int) -> list[str]:
        _launch_agents_dir().mkdir(parents=True, exist_ok=True)
        plist = {
            "Label": LABEL,
            "ProgramArguments": pull_argv(),
            "StartInterval": interval_minutes * 60,
            "RunAtLoad": True,
        }
        path = _plist_path()
        with open(path, "wb") as f:
            plistlib.dump(plist, f)
        subprocess.run(
            ["launchctl", "load", "-w", str(path)], check=True, capture_output=True, text=True
        )
        return []

    def uninstall(self) -> None:
        path = _plist_path()
        if path.exists():
            subprocess.run(
                ["launchctl", "unload", str(path)], check=False, capture_output=True, text=True
            )
            path.unlink()

    def status(self) -> ScheduleStatus:
        result = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True)
        if result.returncode != 0:
            return ScheduleStatus(installed=False, detail="agent not loaded")
        return ScheduleStatus(installed=True, detail=result.stdout.strip())
