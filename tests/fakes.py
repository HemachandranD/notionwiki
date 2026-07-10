"""Test doubles for NotionClient — no network involved."""

from __future__ import annotations

from notion_wiki.notion.models import Block


class FakeNotionClient:
    def __init__(self, pages=None, blocks: dict[str, list[Block]] | None = None, databases=None):
        self.pages = pages if pages is not None else []
        self.blocks: dict[str, list[Block]] = blocks or {}
        self.databases = databases or {}

    def search(self):
        yield from self.pages

    def fetch_block_tree(self, block_id: str, *, toggle_depth: int = 0) -> list[Block]:
        return self.blocks.get(block_id, [])

    def query_database(self, database_id: str):
        yield from self.databases.get(database_id, [])

    def close(self) -> None:
        pass


def make_raw_page(
    page_id: str,
    title: str,
    *,
    last_edited_time: str,
    parent: dict | None = None,
    url: str | None = None,
    properties: dict | None = None,
) -> dict:
    props = {"title": {"type": "title", "title": [{"plain_text": title}]}}
    if properties:
        props.update(properties)
    return {
        "id": page_id,
        "url": url or f"https://notion.so/{page_id}",
        "parent": parent or {"type": "workspace", "workspace": True},
        "last_edited_time": last_edited_time,
        "created_time": last_edited_time,
        "properties": props,
        "archived": False,
    }


def rt(text: str, **annotations) -> dict:
    return {"plain_text": text, "type": "text", "annotations": annotations, "href": None}


def paragraph_block(text: str, block_id: str = "p1") -> Block:
    return Block(id=block_id, type="paragraph", has_children=False, data={"rich_text": [rt(text)]})
