"""Lightweight dataclasses over the Notion REST API's JSON shapes.

Deliberately plain dataclasses, not a full ORM — the converter only needs a
handful of fields off each object; everything else stays in `raw`/`data` for
forward-compatibility with block/property types we don't special-case yet.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RichText:
    plain_text: str
    href: str | None = None
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    code: bool = False
    mention_page_id: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> RichText:
        annotations = data.get("annotations", {})
        mention_page_id = None
        if data.get("type") == "mention":
            mention = data.get("mention") or {}
            if mention.get("type") == "page":
                mention_page_id = mention["page"]["id"]
        return cls(
            plain_text=data.get("plain_text", ""),
            href=data.get("href"),
            bold=annotations.get("bold", False),
            italic=annotations.get("italic", False),
            strikethrough=annotations.get("strikethrough", False),
            code=annotations.get("code", False),
            mention_page_id=mention_page_id,
        )


def rich_text_list(data: list[dict[str, Any]] | None) -> list[RichText]:
    return [RichText.from_api(rt) for rt in (data or [])]


@dataclass
class Block:
    id: str
    type: str
    has_children: bool
    data: dict[str, Any]
    children: list[Block] = field(default_factory=list)
    truncated: bool = False
    """Set when the fetcher deliberately did not recurse (read-only island or
    a toggle past the max nesting depth) — tells the renderer to emit a
    placeholder even though `has_children` is True."""

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Block:
        block_type = raw["type"]
        return cls(
            id=raw["id"],
            type=block_type,
            has_children=raw.get("has_children", False),
            data=raw.get(block_type, {}) or {},
        )


def extract_title(properties: dict[str, Any]) -> str:
    """Find the "title"-typed property among a page's properties and flatten it."""
    for prop in properties.values():
        if prop.get("type") == "title":
            runs = prop.get("title", [])
            return "".join(rt.get("plain_text", "") for rt in runs)
    return "Untitled"


@dataclass
class Page:
    id: str
    title: str
    url: str
    parent_type: str
    parent_id: str | None
    last_edited_time: str
    created_time: str
    properties: dict[str, Any] = field(default_factory=dict)
    archived: bool = False
    in_trash: bool = False
    object_kind: str = "page"  # "page" (regular) always for Page

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Page:
        parent = raw.get("parent", {})
        parent_type = parent.get("type", "workspace")
        parent_id = parent.get(parent_type) if parent_type != "workspace" else None
        properties = raw.get("properties", {})
        return cls(
            id=raw["id"],
            title=extract_title(properties),
            url=raw.get("url", ""),
            parent_type=parent_type,
            parent_id=parent_id,
            last_edited_time=raw.get("last_edited_time", ""),
            created_time=raw.get("created_time", ""),
            properties=properties,
            archived=raw.get("archived", False),
            in_trash=raw.get("in_trash", False),
        )


@dataclass
class DatabaseRow(Page):
    database_id: str = ""
    database_name: str = ""

    @classmethod
    def from_api(
        cls, raw: dict[str, Any], database_id: str = "", database_name: str = ""
    ) -> DatabaseRow:  # type: ignore[override]
        page = Page.from_api(raw)
        return cls(**dataclasses.asdict(page), database_id=database_id, database_name=database_name)
