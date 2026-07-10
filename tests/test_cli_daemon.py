from pathlib import Path

from typer.testing import CliRunner

from notion_wiki.cli import app
from notion_wiki.config import Config, save_config

runner = CliRunner()


def test_daemon_requires_init(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(tmp_path / "empty"))
    result = runner.invoke(app, ["daemon"])
    assert result.exit_code == 1
    assert "Not initialized" in result.stdout


def test_daemon_requires_token(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    monkeypatch.delenv("NOTION_WIKI_TOKEN", raising=False)
    monkeypatch.setattr("notion_wiki.token.keyring.get_password", lambda *a, **k: None)
    save_config(Config(wiki_root=tmp_path / "wiki"), state_dir / "config.toml")

    result = runner.invoke(app, ["daemon"])
    assert result.exit_code == 1
    assert "No Notion token" in result.stdout


def test_daemon_invokes_run_forever(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("NOTION_WIKI_STATE_DIR", str(state_dir))
    monkeypatch.setenv("NOTION_WIKI_TOKEN", "fake-token")
    save_config(Config(wiki_root=wiki_root), state_dir / "config.toml")

    calls = []
    monkeypatch.setattr(
        "notion_wiki.daemon.run_forever",
        lambda config, token, state_dir, **kwargs: calls.append((config.wiki_root, token, kwargs)),
    )

    result = runner.invoke(app, ["daemon", "--interval-seconds", "10"])
    assert result.exit_code == 0, result.stdout
    assert len(calls) == 1
    assert calls[0][0] == wiki_root
    assert calls[0][1] == "fake-token"
    assert calls[0][2]["interval_seconds"] == 10.0
