from pathlib import Path

from notion_wiki.config import Config, DatabaseRef, config_exists, load_config, save_config


def test_round_trip(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        wiki_root=tmp_path / "wiki",
        root_page_id="abc123",
        databases=[DatabaseRef(id="db1", name="Reading Notes")],
        interval_minutes=5,
    )
    save_config(cfg, cfg_path)
    assert config_exists(cfg_path)

    loaded = load_config(cfg_path)
    assert loaded.wiki_root == cfg.wiki_root
    assert loaded.root_page_id == "abc123"
    assert loaded.databases == [DatabaseRef(id="db1", name="Reading Notes")]
    assert loaded.database_pairs() == [("db1", "Reading Notes")]
    assert loaded.interval_minutes == 5


def test_defaults(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    save_config(Config(wiki_root=tmp_path / "wiki"), cfg_path)
    loaded = load_config(cfg_path)
    assert loaded.full_sweep_every_n_runs == 60
    assert loaded.databases == []
