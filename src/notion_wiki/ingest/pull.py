"""PullRunner: the one-shot `notionwiki pull` cycle (docs/design.md §3, §5).

Ties together the poller, converter, writer, state.db, and daemon_log for a
single run — either incremental (default) or a full reconciliation sweep.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from notion_wiki.convert.assets import download_asset
from notion_wiki.convert.blocks import render_blocks
from notion_wiki.convert.database import render_property_table
from notion_wiki.ingest.daemon_log import DaemonLog, LogEntry
from notion_wiki.ingest.poller import (
    full_sweep_database_rows,
    full_sweep_pages,
    incremental_candidates,
)
from notion_wiki.ingest.scope import ScopeResolver
from notion_wiki.ingest.writer import Outcome, SourceDocument, content_hash, decide_outcome
from notion_wiki.notion.client import NotionClient
from notion_wiki.notion.models import Page
from notion_wiki.paths import (
    archive_dir as state_archive_dir,
)
from notion_wiki.paths import (
    daemon_log_path,
    notion_assets_dir,
    notion_feeder_dir,
)
from notion_wiki.store.archive import archive_file
from notion_wiki.store.db import PageRecord, StateDB
from notion_wiki.store.lock import LockAcquisitionError, SingleInstanceLock


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"


def resolve_slug(db: StateDB, title: str, notion_id: str) -> str:
    """Filenames are frozen at first pull (§4) — reuse the existing slug for a
    known page; otherwise slugify the title, deduplicating with the notion_id
    on collision."""
    existing = db.get_page(notion_id)
    if existing is not None:
        return existing.slug

    base = slugify(title)
    if not db.slug_taken(base):
        return base
    suffixed = f"{base}-{notion_id[:6]}"
    candidate = suffixed
    n = 1
    while db.slug_taken(candidate):
        n += 1
        candidate = f"{suffixed}-{n}"
    return candidate


def build_breadcrumb(db: StateDB, parent_id: str | None) -> list[str]:
    """Best-effort breadcrumb from already-known ancestors; stops at the first
    ancestor we haven't pulled yet."""
    crumb: list[str] = []
    seen: set[str] = set()
    current = parent_id
    while current and current not in seen:
        seen.add(current)
        record = db.get_page(current)
        if record is None:
            break
        crumb.append(record.title)
        current = record.parent_id
    crumb.reverse()
    return crumb


@dataclass
class PullStats:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    renamed: int = 0
    archived: int = 0
    settling: int = 0
    errors: int = 0
    skipped: bool = False


class PullRunner:
    def __init__(
        self,
        client: NotionClient,
        wiki_root: Path,
        db: StateDB,
        *,
        overlap_minutes: int = 5,
        settle_window_minutes: int = 5,
        lock_path: Path | None = None,
        state_dir: Path | None = None,
    ):
        self.client = client
        self.wiki_root = wiki_root
        self.db = db
        self.overlap_minutes = overlap_minutes
        self.settle_window_minutes = settle_window_minutes
        self.log = DaemonLog(daemon_log_path(wiki_root))
        self.feeder_dir = notion_feeder_dir(wiki_root)
        self.assets_dir = notion_assets_dir(wiki_root)
        self.archive_dir = state_archive_dir(state_dir)
        self._lock_path = lock_path

    def run(
        self,
        *,
        full: bool = False,
        databases: list[tuple[str, str]] | None = None,
        root_page_ids: list[str] | None = None,
        now: datetime | None = None,
    ) -> PullStats:
        now = now or datetime.now(UTC)
        databases = databases or []
        scope = ScopeResolver(self.client, root_page_ids or [])

        lock = SingleInstanceLock(self._lock_path) if self._lock_path else None
        if lock:
            try:
                lock.acquire()
            except LockAcquisitionError:
                self.log.append(
                    LogEntry(now.isoformat(), "run", "-", "-", "skipped", ["already running"])
                )
                return PullStats(skipped=True)

        try:
            run_id = self.db.start_run("full" if full else "incremental", now.isoformat())
            stats = PullStats()

            baseline = self.db.get_meta("last_incremental_baseline")
            pages = (
                full_sweep_pages(self.client)
                if full
                else incremental_candidates(
                    self.client, baseline, overlap_minutes=self.overlap_minutes
                )
            )
            for page in pages:
                if not scope.in_scope(page):
                    continue
                self._process(page, kind="page", database_name=None, stats=stats, now=now)

            for database_id, database_name in databases:
                for row in full_sweep_database_rows(self.client, database_id, database_name):
                    self._process(
                        row, kind="database_row", database_name=database_name, stats=stats, now=now
                    )

            if full:
                self._reconcile_deletions(databases, stats, now=now)
                self.db.set_meta("last_full_sweep_at", now.isoformat())

            self.db.set_meta("last_incremental_baseline", now.isoformat())
            self.db.finish_run(run_id, "ok", datetime.now(UTC).isoformat())
            return stats
        finally:
            if lock:
                lock.release()

    def _process(
        self, page: Page, *, kind: str, database_name: str | None, stats: PullStats, now: datetime
    ) -> None:
        existing = self.db.get_page(page.id)

        # Timestamp gate (§5.1): skip the block fetch entirely for pages whose
        # last_edited_time hasn't moved, unless they're mid-settle (§5.3).
        if (
            existing
            and not existing.deleted
            and existing.settling_since is None
            and existing.remote_edited_at
            and page.last_edited_time <= existing.remote_edited_at
        ):
            stats.unchanged += 1
            return

        try:
            blocks = self.client.fetch_block_tree(page.id)
        except Exception as exc:  # noqa: BLE001 - logged, not fatal to the batch (§6)
            stats.errors += 1
            self.log.append(
                LogEntry(
                    datetime.now(UTC).isoformat(), "error", page.id, page.title, "fetch", [str(exc)]
                )
            )
            return

        body = render_blocks(
            blocks,
            resolve_mention=self.db.resolve_slug,
            download_asset=lambda url: download_asset(url, self.assets_dir),
        )
        if kind == "database_row":
            table = render_property_table(page.properties)
            if table:
                body = f"{table}\n\n{body}" if body else table

        new_hash = content_hash(body)
        outcome = decide_outcome(
            existing,
            new_hash=new_hash,
            new_title=page.title,
            remote_edited_at=page.last_edited_time,
            settle_window_minutes=self.settle_window_minutes,
            now=now,
        )

        if outcome == Outcome.SETTLING:
            stats.settling += 1
            if existing:
                existing.settling_since = page.last_edited_time
                self.db.upsert_page(existing)
            return

        if outcome == Outcome.UNCHANGED:
            stats.unchanged += 1
            return

        slug = resolve_slug(self.db, page.title, page.id)
        filename = f"{slug}.md"
        dest = self.feeder_dir / filename
        now_iso = now.isoformat()

        archive_note = None
        if outcome == Outcome.UPDATED and dest.exists():
            archived_path = archive_file(dest, self.archive_dir, slug, now=now)
            archive_note = f"archived→{archived_path.name}"

        details: list[str] = []
        if outcome in (Outcome.NEW, Outcome.UPDATED):
            doc = SourceDocument(
                notion_id=page.id,
                notion_url=page.url,
                kind=kind,
                title=page.title,
                body_markdown=body,
                parent_id=page.parent_id,
                breadcrumb=build_breadcrumb(self.db, page.parent_id),
                database_name=database_name,
                remote_edited_at=page.last_edited_time,
                last_pulled=now_iso,
            )
            self.feeder_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(doc.render(), encoding="utf-8", newline="\n")
            details.append(f"{len(blocks)} blocks")
            if archive_note:
                details.append(archive_note)

        title_field = page.title
        if outcome == Outcome.RENAMED:
            details.append("slug unchanged")
            if existing and existing.title != page.title:
                title_field = f"{page.title} (was: {existing.title})"

        record = PageRecord(
            notion_id=page.id,
            title=page.title,
            slug=slug,
            filename=filename,
            kind=kind,
            content_hash=new_hash,
            remote_edited_at=page.last_edited_time,
            last_pulled=now_iso,
            database_id=getattr(page, "database_id", None),
            database_name=database_name,
            parent_id=page.parent_id,
            breadcrumb_json=None,
            settling_since=None,
            deleted=False,
        )
        self.db.upsert_page(record)

        if outcome == Outcome.NEW:
            stats.new += 1
        elif outcome == Outcome.UPDATED:
            stats.updated += 1
        elif outcome == Outcome.RENAMED:
            stats.renamed += 1

        self.log.append(
            LogEntry(datetime.now(UTC).isoformat(), "pull", page.id, title_field, outcome, details)
        )

    def _reconcile_deletions(
        self, databases: list[tuple[str, str]], stats: PullStats, *, now: datetime
    ) -> None:
        seen_ids = {page.id for page in full_sweep_pages(self.client)}
        for database_id, database_name in databases:
            seen_ids.update(
                row.id for row in full_sweep_database_rows(self.client, database_id, database_name)
            )

        deleted_ids = self.db.active_notion_ids() - seen_ids
        for notion_id in deleted_ids:
            record = self.db.get_page(notion_id)
            if record is None:
                continue
            src = self.feeder_dir / record.filename
            if src.exists():
                archive_file(src, self.archive_dir, record.slug, now=now)
                src.unlink()
            self.db.mark_deleted(notion_id)
            stats.archived += 1
            self.log.append(
                LogEntry(
                    datetime.now(UTC).isoformat(),
                    "pull",
                    notion_id,
                    record.title,
                    "archived",
                    ["deleted in Notion"],
                )
            )
