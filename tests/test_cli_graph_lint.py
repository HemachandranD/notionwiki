from pathlib import Path

from typer.testing import CliRunner

from notion_wiki.cli import app
from notion_wiki.config import Config, save_config
from tests.test_graph_gen import write_page

runner = CliRunner()


def test_cli_graph_regenerates_index_and_json(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    write_page(wiki_root, "wiki/concepts/a.md", frontmatter={"type": "concept", "description": "d"})
    save_config(Config(wiki_root=wiki_root), state_dir / "config.toml")

    result = runner.invoke(app, ["graph"])

    assert result.exit_code == 0, result.stdout
    assert (wiki_root / "wiki" / "index.md").exists()
    assert (wiki_root / "wiki" / "graph.json").exists()


def test_cli_lint_reports_clean(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    write_page(
        wiki_root,
        "wiki/concepts/a.md",
        frontmatter={"type": "concept", "description": "d"},
        body="[[wiki/concepts/a]]",
    )
    save_config(Config(wiki_root=wiki_root), state_dir / "config.toml")

    result = runner.invoke(app, ["lint"])
    assert result.exit_code == 0
    assert "No lint issues" in result.stdout


def test_cli_lint_reports_issues_and_exits_nonzero(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    write_page(
        wiki_root, "wiki/concepts/a.md", frontmatter={"type": "concept"}
    )  # missing description
    save_config(Config(wiki_root=wiki_root), state_dir / "config.toml")

    result = runner.invoke(app, ["lint"])
    assert result.exit_code == 1
    assert "issue(s) found" in result.stdout


def test_cli_graph_and_lint_require_init(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(tmp_path / "empty"))
    assert runner.invoke(app, ["graph"]).exit_code == 1
    assert runner.invoke(app, ["lint"]).exit_code == 1
