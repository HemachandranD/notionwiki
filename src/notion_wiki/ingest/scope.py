"""Page-scope filtering (docs/design.md §5.1, the page-tree-walk refinement).

`init` lets the operator pick specific pages to ingest instead of everything
shared with the integration. A page is in scope when it *is* one of the chosen
roots or descends from one. Ancestry is walked via each page's immediate
`parent_id`; parents not already seen are fetched with `retrieve_page` and
cached, so a run resolves each ancestor at most once.

An empty root set means "no restriction" — `in_scope` short-circuits to True
and never touches the network, preserving the original pull-everything behavior.
"""

from __future__ import annotations

from notion_wiki.notion.client import NotionClient
from notion_wiki.notion.models import Page


def _norm(page_id: str | None) -> str | None:
    """Notion ids compare equal regardless of dash formatting / case."""
    if not page_id:
        return None
    return page_id.replace("-", "").lower()


class ScopeResolver:
    def __init__(self, client: NotionClient, root_ids: list[str]):
        self._client = client
        self._roots = {norm for rid in root_ids if (norm := _norm(rid))}
        # norm(page id) -> original parent page id (or None if the page's parent
        # is a workspace/database, i.e. the top of a page chain).
        self._parent: dict[str, str | None] = {}

    @property
    def unrestricted(self) -> bool:
        return not self._roots

    def note(self, page: Page) -> None:
        """Record a page's parent link from data we already have, avoiding a
        later `retrieve_page` for it."""
        key = _norm(page.id)
        if key is not None:
            self._parent[key] = page.parent_id if page.parent_type == "page_id" else None

    def in_scope(self, page: Page) -> bool:
        if self.unrestricted:
            return True
        self.note(page)
        current: str | None = page.id
        seen: set[str] = set()
        while current:
            key = _norm(current)
            if key is None or key in seen:
                break
            if key in self._roots:
                return True
            seen.add(key)
            current = self._parent_of(current)
        return False

    def _parent_of(self, page_id: str) -> str | None:
        key = _norm(page_id)
        if key is None:
            return None
        if key in self._parent:
            return self._parent[key]
        # Learn this page's parent by fetching it once.
        try:
            raw = self._client.retrieve_page(page_id)
        except Exception:  # noqa: BLE001 - a missing/inaccessible ancestor just ends the walk
            self._parent[key] = None
            return None
        self.note(Page.from_api(raw))
        return self._parent.get(key)
