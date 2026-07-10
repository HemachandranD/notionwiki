"""Read-side index over raw/notion/*.md — backs `notion-wiki open` (docs/design.md §8).

Pure frontmatter scanning, no network. `find_source` implements the
exact-filename -> substring-filename -> substring-title matching cascade,
listing candidates rather than guessing when a stage is ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from notion_wiki.paths import notion_feeder_dir


@dataclass
class RawSourceInfo:
    path: Path
    slug: str
    notion_id: str
    notion_url: str
    title: str


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    return yaml.safe_load(block) or {}


def list_raw_sources(wiki_root: Path) -> list[RawSourceInfo]:
    feeder = notion_feeder_dir(wiki_root)
    if not feeder.exists():
        return []
    sources = []
    for path in sorted(feeder.glob("*.md")):
        if path.name == "daemon_log.md" or path.name.startswith("daemon_log."):
            continue
        frontmatter = _parse_frontmatter(path.read_text(encoding="utf-8"))
        sources.append(
            RawSourceInfo(
                path=path,
                slug=path.stem,
                notion_id=frontmatter.get("notion_id", ""),
                notion_url=frontmatter.get("notion_url", ""),
                title=frontmatter.get("title", ""),
            )
        )
    return sources


@dataclass
class OpenMatch:
    error: str | None = None  # "not_found" | "ambiguous" | None
    result: RawSourceInfo | None = None
    candidates: list[RawSourceInfo] = field(default_factory=list)


def find_source(sources: list[RawSourceInfo], query: str) -> OpenMatch:
    query_stem = query[:-3] if query.lower().endswith(".md") else query
    query_stem_lower = query_stem.lower()
    query_lower = query.lower()

    exact = [s for s in sources if s.slug.lower() == query_stem_lower]
    if len(exact) == 1:
        return OpenMatch(result=exact[0])
    if len(exact) > 1:
        return OpenMatch(error="ambiguous", candidates=exact)

    substring = [s for s in sources if query_stem_lower in s.slug.lower()]
    if len(substring) == 1:
        return OpenMatch(result=substring[0])
    if len(substring) > 1:
        return OpenMatch(error="ambiguous", candidates=substring)

    title_matches = [s for s in sources if query_lower in (s.title or "").lower()]
    if len(title_matches) == 1:
        return OpenMatch(result=title_matches[0])
    if len(title_matches) > 1:
        return OpenMatch(error="ambiguous", candidates=title_matches)

    return OpenMatch(error="not_found")
