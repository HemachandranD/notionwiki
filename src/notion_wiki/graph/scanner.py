"""Scan wiki/**/*.md for frontmatter and [[links]] (docs/design.md §7, §9).

Fully decoupled from Notion/state.db — this is the wiki-layer tooling's only
input, working off whatever's under wiki_root/wiki/.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from notion_wiki.paths import wiki_dir

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Operational files that sit directly in wiki/ but aren't catalog-worthy content pages.
_EXCLUDED_TOP_LEVEL_NAMES = {"index.md", "log.md", "overview.md"}


@dataclass
class WikiPage:
    path: Path
    rel_path: str  # relative to wiki_root, posix-style, e.g. "wiki/concepts/foo.md"
    frontmatter: dict
    links: list[str] = field(default_factory=list)
    body: str = ""

    @property
    def type(self) -> str | None:
        return self.frontmatter.get("type")

    @property
    def description(self) -> str | None:
        return self.frontmatter.get("description")


def _parse_frontmatter_and_body(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    frontmatter = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4 :].lstrip("\n")
    return frontmatter, body


def scan_wiki_pages(wiki_root: Path) -> list[WikiPage]:
    base = wiki_dir(wiki_root)
    if not base.exists():
        return []

    pages = []
    for path in sorted(base.rglob("*.md")):
        if path.parent == base and path.name in _EXCLUDED_TOP_LEVEL_NAMES:
            continue
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter_and_body(text)
        links = _LINK_RE.findall(body)
        rel_path = path.relative_to(wiki_root).as_posix()
        pages.append(
            WikiPage(path=path, rel_path=rel_path, frontmatter=frontmatter, links=links, body=body)
        )
    return pages
