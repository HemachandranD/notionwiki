"""Overwrite+archive semantics, content hashing, and the settle window (docs/design.md §4, §5.3)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import yaml

from notion_wiki.store.db import PageRecord

_FRONTMATTER_KEY_ORDER = (
    "notion_id",
    "notion_url",
    "source",
    "kind",
    "title",
    "database",
    "parent",
    "breadcrumb",
    "last_pulled",
    "remote_edited_at",
    "content_hash",
)


class Outcome:
    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    RENAMED = "renamed"
    ARCHIVED = "archived"  # deletion, handled by the full-sweep reconciliation
    SETTLING = "settling"  # internal only — never logged (§5.3)


def normalize_body(markdown: str) -> str:
    """LF endings, trailing whitespace stripped per line, single trailing newline.

    Applied before hashing so re-serializing identical content never produces
    a spurious diff (§4) — `content_hash` covers this normalized body only,
    never the frontmatter block (which always changes via `last_pulled`).
    """
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    body = "\n".join(lines).rstrip("\n")
    return body + "\n" if body else "\n"


def content_hash(markdown: str) -> str:
    normalized = normalize_body(markdown)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def is_within_settle_window(remote_edited_at: str, window_minutes: int, now: datetime) -> bool:
    edited = _parse_iso(remote_edited_at)
    if now.tzinfo is None:
        now = now.replace(tzinfo=edited.tzinfo)
    return (now - edited) < timedelta(minutes=window_minutes)


def decide_outcome(
    existing: PageRecord | None,
    *,
    new_hash: str,
    new_title: str,
    remote_edited_at: str,
    settle_window_minutes: int,
    now: datetime,
) -> str:
    """Implements the outcome table in §5.3, plus the §5.3 settle window.

    A page under active live editing keeps its `last_edited_time` advancing
    tick-to-tick; while that's happening and we're still inside the settle
    window, hold off writing (SETTLING) rather than archiving a new version
    on every intermediate tick. Once the timestamp stabilizes (unchanged
    since the last observation) or ages out of the window, decide normally.
    """
    if existing is None or existing.deleted:
        return Outcome.NEW

    if is_within_settle_window(remote_edited_at, settle_window_minutes, now):
        last_observed = existing.settling_since or existing.remote_edited_at
        if remote_edited_at != last_observed:
            return Outcome.SETTLING

    if existing.content_hash != new_hash:
        return Outcome.UPDATED
    if existing.title != new_title:
        return Outcome.RENAMED
    return Outcome.UNCHANGED


@dataclass
class SourceDocument:
    notion_id: str
    notion_url: str
    kind: str  # "page" | "database_row"
    title: str
    body_markdown: str
    parent_id: str | None = None
    breadcrumb: list[str] = field(default_factory=list)
    database_name: str | None = None
    remote_edited_at: str = ""
    last_pulled: str = ""

    def frontmatter(self) -> dict:
        fm = {
            "notion_id": self.notion_id,
            "notion_url": self.notion_url,
            "source": "notion",
            "kind": self.kind,
            "title": self.title,
            "parent": self.parent_id,
            "breadcrumb": self.breadcrumb,
            "last_pulled": self.last_pulled,
            "remote_edited_at": self.remote_edited_at,
            "content_hash": content_hash(self.body_markdown),
        }
        if self.database_name:
            fm["database"] = self.database_name
        return {key: fm[key] for key in _FRONTMATTER_KEY_ORDER if key in fm}

    def render(self) -> str:
        front = yaml.safe_dump(self.frontmatter(), sort_keys=False, allow_unicode=True).strip()
        body = normalize_body(self.body_markdown)
        return f"---\n{front}\n---\n\n# {self.title}\n\n{body}"
