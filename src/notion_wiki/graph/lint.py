"""Agent-run lint pass over the wiki layer (docs/design.md §7).

Detection is scripted here; fixing stays the agent's judgment call — this
module only reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from notion_wiki.graph.scanner import WikiPage, scan_wiki_pages


@dataclass
class LintIssue:
    kind: str  # orphan | dangling_link | missing_metadata | compression | agent_doc_drift
    page: str
    detail: str


def _link_target(link: str) -> str:
    return link.split("|")[0].strip()


def find_dangling_links(pages: list[WikiPage]) -> list[LintIssue]:
    known = {p.rel_path[: -len(".md")] for p in pages}
    issues = []
    for page in pages:
        for link in page.links:
            target = _link_target(link)
            if target not in known and not target.startswith("raw/"):
                issues.append(
                    LintIssue("dangling_link", page.rel_path, f"link to unknown page: {target}")
                )
    return issues


def find_orphans(pages: list[WikiPage]) -> list[LintIssue]:
    linked_targets = {_link_target(link) for page in pages for link in page.links}
    issues = []
    for page in pages:
        key = page.rel_path[: -len(".md")]
        if page.type and key not in linked_targets:
            issues.append(
                LintIssue("orphan", page.rel_path, "no other wiki page links to this page")
            )
    return issues


def find_missing_metadata(pages: list[WikiPage]) -> list[LintIssue]:
    issues = []
    for page in pages:
        missing = [key for key in ("type", "description") if not page.frontmatter.get(key)]
        if missing:
            issues.append(
                LintIssue("missing_metadata", page.rel_path, f"missing: {', '.join(missing)}")
            )
    return issues


def find_compression_violations(pages: list[WikiPage], wiki_root: Path) -> list[LintIssue]:
    """A wiki page larger than the raw sources it cites has negative value (§7)."""
    issues = []
    for page in pages:
        sources = page.frontmatter.get("sources") or []
        if not sources:
            continue
        source_size = 0
        for source_ref in sources:
            rel = str(source_ref).strip("[]")
            source_path = wiki_root / f"{rel}.md"
            if source_path.exists():
                source_size += source_path.stat().st_size
        page_size = page.path.stat().st_size
        if source_size and page_size > source_size:
            issues.append(
                LintIssue(
                    "compression",
                    page.rel_path,
                    f"page ({page_size}B) is larger than its cited sources ({source_size}B)",
                )
            )
    return issues


def find_agent_doc_drift(wiki_root: Path) -> list[LintIssue]:
    claude_path = wiki_root / "CLAUDE.md"
    agents_path = wiki_root / "AGENTS.md"
    if not claude_path.exists() or not agents_path.exists():
        return []
    if claude_path.read_text(encoding="utf-8") != agents_path.read_text(encoding="utf-8"):
        return [LintIssue("agent_doc_drift", "CLAUDE.md", "CLAUDE.md and AGENTS.md have diverged")]
    return []


def run_lint(wiki_root: Path) -> list[LintIssue]:
    pages = scan_wiki_pages(wiki_root)
    issues: list[LintIssue] = []
    issues.extend(find_dangling_links(pages))
    issues.extend(find_orphans(pages))
    issues.extend(find_missing_metadata(pages))
    issues.extend(find_compression_violations(pages, wiki_root))
    issues.extend(find_agent_doc_drift(wiki_root))
    return issues
