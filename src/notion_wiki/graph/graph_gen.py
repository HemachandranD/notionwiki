"""wiki/graph.json generator (docs/design.md §7, §9): plain nodes/edges/backlink-counts."""

from __future__ import annotations

import json
from pathlib import Path

from notion_wiki.graph.scanner import WikiPage, scan_wiki_pages
from notion_wiki.paths import wiki_graph_json_path


def _link_target(link: str) -> str:
    return link.split("|")[0].strip()  # tolerate an optional [[target|alias]] form


def build_graph(pages: list[WikiPage]) -> dict:
    by_key = {p.rel_path[: -len(".md")]: p for p in pages}
    backlink_counts: dict[str, int] = dict.fromkeys(by_key, 0)
    edges = []

    for page in pages:
        source_key = page.rel_path[: -len(".md")]
        for link in page.links:
            target_key = _link_target(link)
            if target_key in by_key:
                edges.append({"source": source_key, "target": target_key})
                backlink_counts[target_key] += 1

    nodes = [
        {
            "id": key,
            "type": page.type or "untyped",
            "description": page.description or "",
            "backlinks": backlink_counts[key],
        }
        for key, page in by_key.items()
    ]
    return {"nodes": nodes, "edges": edges}


def generate_graph(wiki_root: Path) -> dict:
    pages = scan_wiki_pages(wiki_root)
    graph = build_graph(pages)
    path = wiki_graph_json_path(wiki_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    return graph
