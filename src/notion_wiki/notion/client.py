"""Thin Notion REST API client (docs/design.md §5.1, §12).

Every request goes through a token-bucket rate limiter and retries with
exponential backoff on 429/5xx, honoring `Retry-After` when present.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from notion_wiki.notion.models import Block
from notion_wiki.notion.rate_limit import TokenBucket

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

# Block types that are always rendered as read-only-island placeholders
# (docs/design.md §5.2) — their children are never fetched.
NEVER_RECURSE_TYPES = frozenset(
    {
        "synced_block",
        "embed",
        "column_list",
        "column",
        "table",
        "child_database",
        "video",
        "audio",
        "file",
        "pdf",
        "bookmark",
        "link_preview",
        "template",
        "breadcrumb",
        "table_of_contents",
        "equation",
        "callout",
    }
)

# "Deeply nested toggles" (§5.2) become placeholders past this depth.
MAX_TOGGLE_DEPTH = 3


class NotionAPIError(RuntimeError):
    """Raised when a Notion API request exhausts its retries or fails outright."""


class NotionClient:
    def __init__(
        self,
        token: str,
        *,
        http_client: httpx.Client | None = None,
        rate_limiter: TokenBucket | None = None,
        max_retries: int = 5,
    ):
        self._http = http_client or httpx.Client(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._rate_limiter = rate_limiter or TokenBucket()
        self._max_retries = max_retries

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> NotionClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- low-level request/pagination plumbing ---

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        backoff = 1.0
        response: httpx.Response | None = None
        for attempt in range(self._max_retries):
            self._rate_limiter.acquire()
            response = self._http.request(method, path, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self._max_retries - 1:
                    break
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else backoff
                time.sleep(wait)
                backoff *= 2
                continue
            response.raise_for_status()
            return response
        assert response is not None
        raise NotionAPIError(
            f"{method} {path} failed after {self._max_retries} attempts: "
            f"{response.status_code} {response.text}"
        )

    def _paginate_post(self, path: str, body: dict[str, Any] | None = None) -> Iterator[dict]:
        body = dict(body or {})
        while True:
            data = self._request("POST", path, json=body).json()
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            body["start_cursor"] = data.get("next_cursor")

    def _paginate_get(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
        params = dict(params or {})
        while True:
            data = self._request("GET", path, params=params).json()
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            params["start_cursor"] = data.get("next_cursor")

    # --- public API surface ---

    def search(
        self, *, query: str = "", sort_descending_last_edited: bool = True
    ) -> Iterator[dict]:
        """Search pages/subpages only (docs/design.md §5.1 — rows are never found via search)."""
        body: dict[str, Any] = {"filter": {"value": "page", "property": "object"}}
        if query:
            body["query"] = query
        if sort_descending_last_edited:
            body["sort"] = {"direction": "descending", "timestamp": "last_edited_time"}
        yield from self._paginate_post("/search", body)

    def search_databases(self) -> Iterator[dict]:
        """Search for database objects themselves (not rows) — used by `init` to
        list databases for the all/choose prompt (§8.1)."""
        body: dict[str, Any] = {"filter": {"value": "database", "property": "object"}}
        yield from self._paginate_post("/search", body)

    def list_block_children(self, block_id: str) -> Iterator[dict]:
        yield from self._paginate_get(f"/blocks/{block_id}/children", {"page_size": 100})

    def retrieve_page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{page_id}").json()

    def query_database(self, database_id: str) -> Iterator[dict]:
        yield from self._paginate_post(f"/databases/{database_id}/query")

    def retrieve_database(self, database_id: str) -> dict:
        return self._request("GET", f"/databases/{database_id}").json()

    def fetch_block_tree(self, block_id: str, *, toggle_depth: int = 0) -> list[Block]:
        """Recursively fetch a block's children, gating recursion per §5.2.

        Read-only-island types (synced blocks, embeds, columns, ...) and
        toggles past `MAX_TOGGLE_DEPTH` are marked `truncated` instead of
        being recursed into — the converter renders those as placeholders.
        """
        blocks: list[Block] = []
        for raw in self.list_block_children(block_id):
            block = Block.from_api(raw)
            if block.has_children:
                if block.type in NEVER_RECURSE_TYPES:
                    block.truncated = True
                elif block.type == "toggle" and toggle_depth + 1 > MAX_TOGGLE_DEPTH:
                    block.truncated = True
                else:
                    next_depth = toggle_depth + 1 if block.type == "toggle" else toggle_depth
                    block.children = self.fetch_block_tree(block.id, toggle_depth=next_depth)
            blocks.append(block)
        return blocks
