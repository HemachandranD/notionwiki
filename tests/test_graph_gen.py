import json
from pathlib import Path

from notion_wiki.graph.graph_gen import build_graph, generate_graph
from notion_wiki.graph.index_gen import generate_index, render_index
from notion_wiki.graph.scanner import scan_wiki_pages


def write_page(wiki_root: Path, rel_path: str, *, frontmatter: dict, body: str = "") -> None:
    path = wiki_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
    path.write_text(f"---\n{fm_lines}\n---\n\n{body}\n", encoding="utf-8")


def test_scan_wiki_pages_excludes_operational_files(tmp_path: Path):
    write_page(
        tmp_path,
        "wiki/concepts/bridge.md",
        frontmatter={"type": "concept", "description": "The bridge"},
        body="See [[wiki/entities/notion]] for more.",
    )
    (tmp_path / "wiki").mkdir(exist_ok=True)
    (tmp_path / "wiki" / "log.md").write_text("log entry", encoding="utf-8")
    (tmp_path / "wiki" / "overview.md").write_text("overview", encoding="utf-8")

    pages = scan_wiki_pages(tmp_path)
    assert len(pages) == 1
    assert pages[0].type == "concept"
    assert pages[0].links == ["wiki/entities/notion"]


def test_render_index_groups_by_type(tmp_path: Path):
    write_page(
        tmp_path, "wiki/concepts/a.md", frontmatter={"type": "concept", "description": "A concept"}
    )
    write_page(
        tmp_path, "wiki/entities/b.md", frontmatter={"type": "entity", "description": "An entity"}
    )
    pages = scan_wiki_pages(tmp_path)

    content = render_index(pages)
    assert "## concept" in content
    assert "## entity" in content
    assert "[[wiki/concepts/a]] — a: A concept" in content


def test_generate_index_writes_file(tmp_path: Path):
    write_page(
        tmp_path, "wiki/concepts/a.md", frontmatter={"type": "concept", "description": "desc"}
    )
    generate_index(tmp_path)
    assert (tmp_path / "wiki" / "index.md").exists()


def test_build_graph_counts_backlinks_and_ignores_dangling_targets(tmp_path: Path):
    write_page(
        tmp_path,
        "wiki/concepts/a.md",
        frontmatter={"type": "concept", "description": "d"},
        body="Links to [[wiki/concepts/b]] and [[wiki/does/not/exist]].",
    )
    write_page(tmp_path, "wiki/concepts/b.md", frontmatter={"type": "concept", "description": "d2"})
    pages = scan_wiki_pages(tmp_path)

    graph = build_graph(pages)
    assert len(graph["edges"]) == 1
    node_b = next(n for n in graph["nodes"] if n["id"] == "wiki/concepts/b")
    assert node_b["backlinks"] == 1
    node_a = next(n for n in graph["nodes"] if n["id"] == "wiki/concepts/a")
    assert node_a["backlinks"] == 0


def test_generate_graph_writes_valid_json(tmp_path: Path):
    write_page(tmp_path, "wiki/concepts/a.md", frontmatter={"type": "concept", "description": "d"})
    generate_graph(tmp_path)
    data = json.loads((tmp_path / "wiki" / "graph.json").read_text(encoding="utf-8"))
    assert data["nodes"][0]["id"] == "wiki/concepts/a"
