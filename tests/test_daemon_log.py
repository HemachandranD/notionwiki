from pathlib import Path

from notion_wiki.ingest.daemon_log import DaemonLog, LogEntry


def test_format_roundtrip():
    entry = LogEntry(
        timestamp="2026-07-09T14:03:11Z",
        action="pull",
        notion_id="1a2b3c4d",
        title="Bridge Design",
        outcome="updated",
        details=["12 blocks", "archived→2026-07-09T14-03_bridge-design.md"],
    )
    line = entry.format()
    assert line == (
        "## [2026-07-09T14:03:11Z] pull | 1a2b3c4d | Bridge Design | updated | "
        "12 blocks | archived→2026-07-09T14-03_bridge-design.md"
    )

    parsed = LogEntry.parse(line)
    assert parsed == entry


def test_title_with_pipe_is_escaped():
    entry = LogEntry("2026-07-09T14:03:11Z", "pull", "abc", "A | B", "new", [])
    line = entry.format()
    assert "A / B" in line
    assert line.count("|") == 3  # exactly the column separators, none from the title


def test_run_skipped_entry_uses_dashes():
    entry = LogEntry("2026-07-09T14:04:00Z", "run", "-", "-", "skipped", ["already running"])
    line = entry.format()
    assert line == "## [2026-07-09T14:04:00Z] run | - | - | skipped | already running"


def test_append_and_read_recent(tmp_path: Path):
    log = DaemonLog(tmp_path / "daemon_log.md")
    for i in range(5):
        log.append(LogEntry(f"2026-07-09T14:0{i}:00Z", "pull", f"id{i}", f"Page {i}", "new", []))

    recent = log.read_recent(limit=2)
    assert [e.notion_id for e in recent] == ["id3", "id4"]


def test_read_entries_ignores_malformed_lines(tmp_path: Path):
    path = tmp_path / "daemon_log.md"
    path.write_text(
        "not a log line\n## [2026-07-09T14:00:00Z] pull | id1 | Title | new\n", encoding="utf-8"
    )
    log = DaemonLog(path)
    entries = log.read_entries()
    assert len(entries) == 1
    assert entries[0].notion_id == "id1"


def test_rotation_on_size_cap(tmp_path: Path):
    path = tmp_path / "daemon_log.md"
    log = DaemonLog(path, rotate_size_bytes=100)
    log.append(LogEntry("2026-07-01T00:00:00Z", "pull", "id1", "Title One", "new", []))
    # File is now small; force a rotation by writing padding directly, then append again.
    path.write_bytes(path.read_bytes() + b"x" * 200)

    log.append(LogEntry("2026-07-01T00:01:00Z", "pull", "id2", "Title Two", "new", []))

    rollover_candidates = list(tmp_path.glob("daemon_log.20*.md"))
    assert len(rollover_candidates) == 1
    assert path.exists()
    fresh_entries = log.read_entries()
    assert [e.notion_id for e in fresh_entries] == ["id2"]
