"""Windows Task Scheduler integration (docs/design.md §10).

Trigger: *At log on* + *Repeat every N minutes* — no admin, no service,
nothing resident between runs. schtasks' `/SC ONLOGON` combined with
`/RI`/`/DU` is the standard way to get "repeat indefinitely after logon".
"""

from __future__ import annotations

import shutil
import subprocess

from notion_wiki.schedule.base import ScheduleStatus, pull_argv

TASK_NAME = "notionwiki pull"


def _schtasks() -> str:
    return shutil.which("schtasks") or "schtasks"


class WindowsScheduler:
    name = "windows"

    def install(self, interval_minutes: int) -> list[str]:
        command = " ".join(f'"{part}"' if " " in part else part for part in pull_argv())
        subprocess.run(
            [
                _schtasks(),
                "/Create",
                "/TN",
                TASK_NAME,
                "/TR",
                command,
                "/SC",
                "ONLOGON",
                "/RI",
                str(interval_minutes),
                "/DU",
                "9999:59",
                "/F",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return []

    def uninstall(self) -> None:
        subprocess.run(
            [_schtasks(), "/Delete", "/TN", TASK_NAME, "/F"],
            check=False,
            capture_output=True,
            text=True,
        )

    def status(self) -> ScheduleStatus:
        result = subprocess.run(
            [_schtasks(), "/Query", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ScheduleStatus(installed=False, detail="task not found")
        return ScheduleStatus(installed=True, detail=result.stdout.strip())
