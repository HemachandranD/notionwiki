"""Windows Task Scheduler integration (docs/design.md §10).

Trigger: repeat every N minutes indefinitely, starting at creation — no
admin, no service, nothing resident between runs. `schtasks /Create` rejects
`/RI`/`/DU` (repetition) on an `/SC ONLOGON` trigger outright ("The options
/RI, /DU, ... are not applicable for the scheduled types: ONSTART, ONLOGON,
ONIDLE, ONEVENT." — verified against schtasks.exe directly); that combination
only works through a LogonTrigger in the XML task-definition format the GUI
uses, not the plain flag syntax. `/SC MINUTE /MO N` is what the Windows
ecosystem actually uses for "run every N minutes" and needs no such
workaround; like macOS's `RunAtLoad` and Linux's `OnBootSec`, it fires soon
after creation and keeps firing every interval after that. Task Scheduler
still only runs it while the creating user is logged on, since no `/RU`
credentials are supplied.
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
        try:
            subprocess.run(
                [
                    _schtasks(),
                    "/Create",
                    "/TN",
                    TASK_NAME,
                    "/TR",
                    command,
                    "/SC",
                    "MINUTE",
                    "/MO",
                    str(max(1, interval_minutes)),
                    "/F",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip() or f"exit code {exc.returncode}"
            raise RuntimeError(f"schtasks /Create failed: {detail}") from exc
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
