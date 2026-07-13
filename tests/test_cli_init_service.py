from pathlib import Path

import pytest
from typer.testing import CliRunner

import notion_wiki.cli as cli_module
from notion_wiki.cli import app
from notion_wiki.config import load_config
from tests.fakes import FakeNotionClient, make_raw_page

runner = CliRunner()


class InitFakeClient(FakeNotionClient):
    def __init__(self, pages, database_objects):
        super().__init__(pages=pages)
        self._database_objects = database_objects

    def search_databases(self):
        yield from self._database_objects


@pytest.fixture
def state_env(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    monkeypatch.setattr("notion_wiki.token.keyring.set_password", lambda *a, **k: None)
    monkeypatch.setattr("notion_wiki.token.keyring.get_password", lambda *a, **k: None)
    return state_dir


def test_init_scaffolds_wiki_and_writes_config(tmp_path: Path, state_env, monkeypatch):
    wiki_root = tmp_path / "my-wiki"
    fake_client = InitFakeClient(
        pages=[
            make_raw_page("root1", "Knowledge Base", last_edited_time="2026-07-09T14:00:00.000Z")
        ],
        database_objects=[],
    )
    monkeypatch.setattr(cli_module, "NotionClient", lambda token: fake_client)

    result = runner.invoke(
        app,
        ["init"],
        input="\n".join(
            [
                str(wiki_root),  # 1. wiki root
                "fake-token",  # 2. token
                "1",  # 3. choose first candidate root page
                "n",  # 4. pull databases? no
                "1",  # 5. interval minutes
                "n",  # 6. install schedule? no
            ]
        )
        + "\n",
    )

    assert result.exit_code == 0, result.stdout
    assert (wiki_root / "raw" / "notion").is_dir()
    assert (wiki_root / "wiki" / "concepts").is_dir()
    assert (wiki_root / "CLAUDE.md").exists()
    assert (wiki_root / "AGENTS.md").exists()

    config = load_config(state_env / "config.toml")
    assert config.wiki_root == wiki_root
    assert config.root_page_ids == ["root1"]
    assert config.interval_minutes == 1


def test_init_with_database_selection(tmp_path: Path, state_env, monkeypatch):
    wiki_root = tmp_path / "wiki2"
    fake_client = InitFakeClient(
        pages=[make_raw_page("root1", "Home", last_edited_time="2026-07-09T14:00:00.000Z")],
        database_objects=[{"id": "db1", "title": [{"plain_text": "Reading Notes"}]}],
    )
    monkeypatch.setattr(cli_module, "NotionClient", lambda token: fake_client)

    result = runner.invoke(
        app,
        ["init"],
        input="\n".join(
            [
                str(wiki_root),
                "fake-token",
                "1",
                "y",  # pull databases? yes
                "all",  # pull all
                "1",
                "n",
            ]
        )
        + "\n",
    )

    assert result.exit_code == 0, result.stdout
    config = load_config(state_env / "config.toml")
    assert config.databases[0].id == "db1"
    assert config.databases[0].name == "Reading Notes"


def test_service_status_reports_not_installed(monkeypatch):
    from notion_wiki.schedule.base import ScheduleStatus

    class StubScheduler:
        name = "stub"

        def status(self):
            return ScheduleStatus(installed=False, detail="not found")

    monkeypatch.setattr(cli_module, "detect_scheduler", lambda: StubScheduler())
    result = runner.invoke(app, ["service", "status"])
    assert result.exit_code == 0
    assert "Not installed" in result.stdout


def test_service_install_requires_init(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(tmp_path / "empty"))
    result = runner.invoke(app, ["service", "install"])
    assert result.exit_code == 1
    assert "Not initialized" in result.stdout
