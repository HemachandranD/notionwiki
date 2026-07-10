from pathlib import Path

from notion_wiki.raw_index import find_source, list_raw_sources


def write_source(feeder: Path, filename: str, *, notion_id: str, title: str) -> None:
    feeder.mkdir(parents=True, exist_ok=True)
    (feeder / filename).write_text(
        f"---\nnotion_id: {notion_id}\n"
        f"notion_url: https://notion.so/{notion_id}\n"
        f"title: {title}\n---\n\nbody\n",
        encoding="utf-8",
    )


def test_list_raw_sources_skips_daemon_log(tmp_path: Path):
    feeder = tmp_path / "raw" / "notion"
    write_source(feeder, "bridge-design.md", notion_id="p1", title="Bridge Design")
    (feeder / "daemon_log.md").write_text("## [x] pull | - | - | new", encoding="utf-8")

    sources = list_raw_sources(tmp_path)
    assert len(sources) == 1
    assert sources[0].slug == "bridge-design"
    assert sources[0].title == "Bridge Design"


def test_find_source_exact_slug_match(tmp_path: Path):
    feeder = tmp_path / "raw" / "notion"
    write_source(feeder, "bridge-design.md", notion_id="p1", title="Bridge Design")
    write_source(feeder, "other-page.md", notion_id="p2", title="Other Page")
    sources = list_raw_sources(tmp_path)

    match = find_source(sources, "bridge-design")
    assert match.error is None
    assert match.result.slug == "bridge-design"


def test_find_source_substring_fallback(tmp_path: Path):
    feeder = tmp_path / "raw" / "notion"
    write_source(feeder, "bridge-design-doc.md", notion_id="p1", title="Bridge Design Doc")
    sources = list_raw_sources(tmp_path)

    match = find_source(sources, "bridge")
    assert match.error is None
    assert match.result.slug == "bridge-design-doc"


def test_find_source_title_substring_fallback(tmp_path: Path):
    feeder = tmp_path / "raw" / "notion"
    write_source(feeder, "abc123.md", notion_id="p1", title="Weekly Sync Notes")
    sources = list_raw_sources(tmp_path)

    match = find_source(sources, "weekly sync")
    assert match.error is None
    assert match.result.slug == "abc123"


def test_find_source_ambiguous_lists_candidates(tmp_path: Path):
    feeder = tmp_path / "raw" / "notion"
    write_source(feeder, "design-one.md", notion_id="p1", title="Design One")
    write_source(feeder, "design-two.md", notion_id="p2", title="Design Two")
    sources = list_raw_sources(tmp_path)

    match = find_source(sources, "design")
    assert match.error == "ambiguous"
    assert {c.slug for c in match.candidates} == {"design-one", "design-two"}


def test_find_source_not_found(tmp_path: Path):
    feeder = tmp_path / "raw" / "notion"
    write_source(feeder, "bridge-design.md", notion_id="p1", title="Bridge Design")
    sources = list_raw_sources(tmp_path)

    match = find_source(sources, "nonexistent")
    assert match.error == "not_found"
