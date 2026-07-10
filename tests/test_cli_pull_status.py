import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import notion_wiki.cli as cli_module
from notion_wiki.cli import app
from notion_wiki.config import Config, save_config
from tests.fakes import FakeNotionClient, make_raw_page, paragraph_block

runner = CliRunner()


@pytest.fixture
def wiki_env(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    monkeypatch.setenv("NOTION_WIKI_TOKEN", "fake-token")
    save_config(Config(wiki_root=wiki_root), state_dir / "config.toml")
    return {"wiki_root": wiki_root, "state_dir": state_dir}


def test_pull_requires_init(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(tmp_path / "empty"))
    result = runner.invoke(app, ["pull"])
    assert result.exit_code == 1
    assert "Not initialized" in result.stdout


def test_pull_requires_token(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    monkeypatch.delenv("NOTION_WIKI_TOKEN", raising=False)
    monkeypatch.setattr("notion_wiki.token.keyring.get_password", lambda *a, **k: None)
    save_config(Config(wiki_root=tmp_path / "wiki"), state_dir / "config.toml")

    result = runner.invoke(app, ["pull"])
    assert result.exit_code == 1
    assert "No Notion token" in result.stdout


def test_pull_runs_with_fake_client(wiki_env, monkeypatch):
    fake_client = FakeNotionClient(
        pages=[make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("hello world")]},
    )
    monkeypatch.setattr(cli_module, "NotionClient", lambda token: fake_client)

    result = runner.invoke(app, ["pull", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["new"] == 1

    dest = wiki_env["wiki_root"] / "raw" / "notion" / "bridge-design.md"
    assert dest.exists()


def test_status_reports_source_count(wiki_env, monkeypatch):
    fake_client = FakeNotionClient(
        pages=[make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("hello world")]},
    )
    monkeypatch.setattr(cli_module, "NotionClient", lambda token: fake_client)
    runner.invoke(app, ["pull"])

    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sources"] == 1
    assert payload["recent_errors"] == 0


def test_status_requires_init(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(tmp_path / "empty"))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
