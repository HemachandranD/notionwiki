"""Linux systemd user timer integration (docs/design.md §10, §11).

A `notion-wiki.timer` -> `notion-wiki.service` (Type=oneshot) pair under the
user's systemd instance. A headless box running this timer commonly lacks a
Secret Service (`keyring`'s default backend needs a logged-in desktop
session's keyring daemon) — detected at install time so the user is steered
to NOTION_WIKI_TOKEN instead of failing opaquely on the first scheduled run.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from notion_wiki.schedule.base import ScheduleStatus, pull_argv

UNIT_NAME = "notion-wiki"


def _systemd_user_dir() -> Path:
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config) if xdg_config else Path.home() / ".config"
    return base / "systemd" / "user"


def has_secret_service() -> bool:
    """Best-effort probe for a running Secret Service (§11)."""
    try:
        import secretstorage

        bus = secretstorage.dbus_init()
        secretstorage.get_default_collection(bus)
        return True
    except Exception:
        return False


class LinuxScheduler:
    name = "linux"

    def install(self, interval_minutes: int) -> list[str]:
        unit_dir = _systemd_user_dir()
        unit_dir.mkdir(parents=True, exist_ok=True)
        exec_start = " ".join(pull_argv())

        (unit_dir / f"{UNIT_NAME}.service").write_text(
            "[Unit]\nDescription=notion-wiki pull\n\n"
            f"[Service]\nType=oneshot\nExecStart={exec_start}\n",
            encoding="utf-8",
        )
        (unit_dir / f"{UNIT_NAME}.timer").write_text(
            "[Unit]\nDescription=notion-wiki pull timer\n\n"
            f"[Timer]\nOnBootSec={interval_minutes}min\nOnUnitActiveSec={interval_minutes}min\n\n"
            "[Install]\nWantedBy=timers.target\n",
            encoding="utf-8",
        )

        subprocess.run(
            ["systemctl", "--user", "daemon-reload"], check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{UNIT_NAME}.timer"],
            check=True,
            capture_output=True,
            text=True,
        )

        if has_secret_service():
            return []
        return [
            "No Secret Service detected on this system — keyring's default backend needs one. "
            "Set NOTION_WIKI_TOKEN in the environment running the systemd timer instead "
            "(see docs/design.md §11)."
        ]

    def uninstall(self) -> None:
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", f"{UNIT_NAME}.timer"],
            check=False,
            capture_output=True,
            text=True,
        )
        for suffix in ("service", "timer"):
            path = _systemd_user_dir() / f"{UNIT_NAME}.{suffix}"
            if path.exists():
                path.unlink()
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"], check=False, capture_output=True, text=True
        )

    def status(self) -> ScheduleStatus:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", f"{UNIT_NAME}.timer"],
            capture_output=True,
            text=True,
        )
        installed = result.stdout.strip() == "active"
        return ScheduleStatus(installed=installed, detail=result.stdout.strip())
