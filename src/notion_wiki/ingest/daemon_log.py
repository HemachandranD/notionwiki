"""daemon_log.md — the ingestion ledger (docs/design.md §6).

Machine-parseable, append-only. Every line starts with `## [ISO-8601]` so
simple tooling works without parsing prose. Columns are `|`-delimited, not
fixed-width — a parser must split on `|` and trim, never assume positions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_LINE_RE = re.compile(r"^##\s*\[(?P<timestamp>[^\]]+)\]\s*(?P<rest>.*)$")


def _escape(value: str) -> str:
    """A Notion title can legally contain `|`; replace it so column counts
    stay unambiguous to a naive `split("|")` parser (§6)."""
    return value.replace("|", "/")


@dataclass
class LogEntry:
    timestamp: str
    action: str  # pull | error | run
    notion_id: str
    title: str
    outcome: str
    details: list[str] = field(default_factory=list)

    def format(self) -> str:
        fields = [self.action, self.notion_id or "-", _escape(self.title or "-"), self.outcome]
        fields.extend(_escape(d) for d in self.details)
        return f"## [{self.timestamp}] " + " | ".join(fields)

    @classmethod
    def parse(cls, line: str) -> LogEntry | None:
        match = _LINE_RE.match(line.strip())
        if not match:
            return None
        parts = [p.strip() for p in match.group("rest").split("|")]
        if len(parts) < 4:
            return None
        action, notion_id, title, outcome, *details = parts
        return cls(
            timestamp=match.group("timestamp"),
            action=action,
            notion_id=notion_id,
            title=title,
            outcome=outcome,
            details=details,
        )


class DaemonLog:
    def __init__(self, path: Path, *, rotate_size_bytes: int = 5 * 1024 * 1024):
        self._path = path
        self._rotate_size_bytes = rotate_size_bytes

    @property
    def path(self) -> Path:
        return self._path

    def append(self, entry: LogEntry) -> None:
        self._maybe_rotate()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8", newline="\n") as f:
            f.write(entry.format() + "\n")

    def _maybe_rotate(self) -> None:
        if not self._path.exists() or self._path.stat().st_size < self._rotate_size_bytes:
            return
        rollover_path = self._path.parent / f"daemon_log.{datetime.now().strftime('%Y-%m')}.md"
        content = self._path.read_bytes()
        with open(rollover_path, "ab") as dst:
            dst.write(content)
        self._path.unlink()

    def read_entries(self) -> list[LogEntry]:
        if not self._path.exists():
            return []
        entries = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            entry = LogEntry.parse(line)
            if entry is not None:
                entries.append(entry)
        return entries

    def read_recent(self, limit: int = 20) -> list[LogEntry]:
        return self.read_entries()[-limit:]
