from pathlib import Path

import pytest
from typer.testing import CliRunner

from notion_wiki.cli import app
from notion_wiki.config import Config, save_config

runner = CliRunner()


@pytest.fixture
def wiki_env(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))

    feeder = wiki_root / "raw" / "notion"
    feeder.mkdir(parents=True)
    (feeder / "bridge-design.md").write_text(
        "---\nnotion_id: p1\nnotion_url: https://notion.so/p1\ntitle: Bridge Design\n---\n\nbody\n",
        encoding="utf-8",
    )

    save_config(Config(wiki_root=wiki_root), state_dir / "config.toml")
    return {"wiki_root": wiki_root, "state_dir": state_dir}


def test_open_exact_match(wiki_env):
    result = runner.invoke(app, ["open", "bridge-design"])
    assert result.exit_code == 0
    assert "https://notion.so/p1" in result.stdout


def test_open_not_found(wiki_env):
    result = runner.invoke(app, ["open", "does-not-exist"])
    assert result.exit_code == 1
    assert "No source matches" in result.stdout


def test_open_without_init_errors(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(tmp_path / "empty-state"))
    result = runner.invoke(app, ["open", "anything"])
    assert result.exit_code == 1
    assert "Not initialized" in result.stdout
