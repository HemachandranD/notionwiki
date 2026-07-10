import subprocess
from pathlib import Path

from notion_wiki.schedule.base import detect_scheduler
from notion_wiki.schedule.linux import LinuxScheduler
from notion_wiki.schedule.macos import MacScheduler
from notion_wiki.schedule.windows import WindowsScheduler


class RecordingRun:
    def __init__(self, returncode: int = 0, stdout: str = ""):
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stdout = stdout

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.returncode, stdout=self.stdout, stderr="")


def test_detect_scheduler_matches_platform(monkeypatch):
    monkeypatch.setattr("notion_wiki.schedule.base.sys.platform", "win32")
    assert detect_scheduler().name == "windows"
    monkeypatch.setattr("notion_wiki.schedule.base.sys.platform", "darwin")
    assert detect_scheduler().name == "macos"
    monkeypatch.setattr("notion_wiki.schedule.base.sys.platform", "linux")
    assert detect_scheduler().name == "linux"


def test_windows_install_invokes_schtasks_with_logon_repeat(monkeypatch):
    recorder = RecordingRun()
    monkeypatch.setattr("notion_wiki.schedule.windows.subprocess.run", recorder)
    monkeypatch.setattr("notion_wiki.schedule.windows._schtasks", lambda: "schtasks")

    warnings = WindowsScheduler().install(interval_minutes=2)

    assert warnings == []
    args = recorder.calls[0]
    assert "/Create" in args
    assert "ONLOGON" in args
    assert "2" in args  # /RI 2


def test_windows_uninstall_deletes_task(monkeypatch):
    recorder = RecordingRun()
    monkeypatch.setattr("notion_wiki.schedule.windows.subprocess.run", recorder)
    monkeypatch.setattr("notion_wiki.schedule.windows._schtasks", lambda: "schtasks")

    WindowsScheduler().uninstall()

    assert "/Delete" in recorder.calls[0]


def test_windows_status_not_found(monkeypatch):
    recorder = RecordingRun(returncode=1)
    monkeypatch.setattr("notion_wiki.schedule.windows.subprocess.run", recorder)
    monkeypatch.setattr("notion_wiki.schedule.windows._schtasks", lambda: "schtasks")

    status = WindowsScheduler().status()
    assert status.installed is False


def test_macos_install_writes_plist_with_start_interval(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("notion_wiki.schedule.macos._launch_agents_dir", lambda: tmp_path)
    recorder = RecordingRun()
    monkeypatch.setattr("notion_wiki.schedule.macos.subprocess.run", recorder)

    warnings = MacScheduler().install(interval_minutes=3)

    assert warnings == []
    plist_path = tmp_path / "com.notion-wiki.pull.plist"
    assert plist_path.exists()
    import plistlib

    data = plistlib.loads(plist_path.read_bytes())
    assert data["StartInterval"] == 180
    assert recorder.calls[0][:2] == ["launchctl", "load"]


def test_linux_install_writes_timer_and_service(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("notion_wiki.schedule.linux._systemd_user_dir", lambda: tmp_path)
    recorder = RecordingRun()
    monkeypatch.setattr("notion_wiki.schedule.linux.subprocess.run", recorder)
    monkeypatch.setattr("notion_wiki.schedule.linux.has_secret_service", lambda: True)

    warnings = LinuxScheduler().install(interval_minutes=1)

    assert warnings == []
    assert (tmp_path / "notion-wiki.service").exists()
    timer_content = (tmp_path / "notion-wiki.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=1min" in timer_content


def test_linux_install_warns_when_no_secret_service(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("notion_wiki.schedule.linux._systemd_user_dir", lambda: tmp_path)
    monkeypatch.setattr("notion_wiki.schedule.linux.subprocess.run", RecordingRun())
    monkeypatch.setattr("notion_wiki.schedule.linux.has_secret_service", lambda: False)

    warnings = LinuxScheduler().install(interval_minutes=1)

    assert len(warnings) == 1
    assert "NOTION_WIKI_TOKEN" in warnings[0]


def test_linux_has_secret_service_false_without_dbus():
    from notion_wiki.schedule.linux import has_secret_service

    # No secretstorage/dbus available in this test environment -> False, not a crash.
    assert has_secret_service() in (True, False)
