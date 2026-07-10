from pathlib import Path

from notion_wiki.graph.lint import run_lint
from tests.test_graph_gen import write_page


def test_lint_flags_missing_metadata(tmp_path: Path):
    write_page(tmp_path, "wiki/concepts/a.md", frontmatter={"type": "concept"})  # no description
    issues = run_lint(tmp_path)
    kinds = {i.kind for i in issues}
    assert "missing_metadata" in kinds


def test_lint_flags_dangling_link(tmp_path: Path):
    write_page(
        tmp_path,
        "wiki/concepts/a.md",
        frontmatter={"type": "concept", "description": "d"},
        body="See [[wiki/concepts/missing]].",
    )
    issues = run_lint(tmp_path)
    assert any(i.kind == "dangling_link" for i in issues)


def test_lint_does_not_flag_raw_links_as_dangling(tmp_path: Path):
    write_page(
        tmp_path,
        "wiki/concepts/a.md",
        frontmatter={"type": "concept", "description": "d"},
        body="See [[raw/notion/bridge-design]].",
    )
    issues = run_lint(tmp_path)
    assert not any(i.kind == "dangling_link" for i in issues)


def test_lint_flags_orphan_page(tmp_path: Path):
    write_page(tmp_path, "wiki/concepts/a.md", frontmatter={"type": "concept", "description": "d"})
    write_page(
        tmp_path,
        "wiki/concepts/b.md",
        frontmatter={"type": "concept", "description": "d"},
        body="[[wiki/concepts/a]]",
    )
    issues = run_lint(tmp_path)
    orphan_pages = {i.page for i in issues if i.kind == "orphan"}
    assert "wiki/concepts/b.md" in orphan_pages
    assert "wiki/concepts/a.md" not in orphan_pages


def test_lint_flags_compression_violation(tmp_path: Path):
    raw_dir = tmp_path / "raw" / "notion"
    raw_dir.mkdir(parents=True)
    (raw_dir / "bridge-design.md").write_text("short", encoding="utf-8")

    page_path = tmp_path / "wiki" / "concepts" / "a.md"
    page_path.parent.mkdir(parents=True)
    page_path.write_text(
        "---\n"
        "type: concept\n"
        "description: d\n"
        'sources: ["[[raw/notion/bridge-design]]"]\n'
        "---\n\n" + ("x" * 1000) + "\n",
        encoding="utf-8",
    )
    issues = run_lint(tmp_path)
    assert any(i.kind == "compression" for i in issues)


def test_lint_flags_agent_doc_drift(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text("one", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("two", encoding="utf-8")
    issues = run_lint(tmp_path)
    assert any(i.kind == "agent_doc_drift" for i in issues)


def test_lint_clean_wiki_has_no_issues(tmp_path: Path):
    write_page(
        tmp_path,
        "wiki/concepts/a.md",
        frontmatter={"type": "concept", "description": "d"},
        body="[[wiki/concepts/b]]",
    )
    write_page(
        tmp_path,
        "wiki/concepts/b.md",
        frontmatter={"type": "concept", "description": "d"},
        body="[[wiki/concepts/a]]",
    )
    (tmp_path / "CLAUDE.md").write_text("same", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("same", encoding="utf-8")

    assert run_lint(tmp_path) == []
