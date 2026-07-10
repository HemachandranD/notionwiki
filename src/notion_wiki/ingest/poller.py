"""Incremental poll + full reconciliation sweep (docs/design.md §5.1).

Full-sweep enumeration here uses the same Search API as the incremental
poll, just exhausted without early termination. §5.1's caveat applies:
search scope is exactly what's shared with the integration, which is why
`init`/`AGENTS.md` insist on sharing only the wiki root page — a full,
separate page-tree walk from the root is a possible future refinement but
isn't required for the deletion-diff this module exists to support.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from notion_wiki.notion.client import NotionClient
from notion_wiki.notion.models import DatabaseRow, Page


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def incremental_candidates(
    client: NotionClient, baseline: str | None, *, overlap_minutes: int = 5
) -> Iterator[Page]:
    """Pages sorted by last_edited_time descending, early-terminated once results
    fall behind `baseline` minus an overlap window (§5.1). `baseline is None`
    (first-ever run) takes everything Search returns."""
    cutoff = _parse_iso(baseline) - timedelta(minutes=overlap_minutes) if baseline else None

    for raw in client.search():
        page = Page.from_api(raw)
        if (
            cutoff is not None
            and page.last_edited_time
            and _parse_iso(page.last_edited_time) < cutoff
        ):
            return
        yield page


def full_sweep_pages(client: NotionClient) -> Iterator[Page]:
    """Every in-scope regular page/subpage, no early termination — the only place
    deletions are detectable (§5.1)."""
    for raw in client.search():
        yield Page.from_api(raw)


def full_sweep_database_rows(
    client: NotionClient, database_id: str, database_name: str
) -> Iterator[DatabaseRow]:
    """Database rows are never discovered via Search (§5.1) — always a direct query."""
    for raw in client.query_database(database_id):
        yield DatabaseRow.from_api(raw, database_id=database_id, database_name=database_name)
