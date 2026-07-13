from pathlib import Path

from notion_wiki.config import Config, DatabaseRef, config_exists, load_config, save_config


def test_round_trip(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        wiki_root=tmp_path / "wiki",
        root_page_ids=["abc123", "def456"],
        databases=[DatabaseRef(id="db1", name="Reading Notes")],
        interval_minutes=5,
    )
    save_config(cfg, cfg_path)
    assert config_exists(cfg_path)

    loaded = load_config(cfg_path)
    assert loaded.wiki_root == cfg.wiki_root
    assert loaded.root_page_ids == ["abc123", "def456"]
    assert loaded.databases == [DatabaseRef(id="db1", name="Reading Notes")]
    assert loaded.database_pairs() == [("db1", "Reading Notes")]
    assert loaded.interval_minutes == 5


def test_defaults(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    save_config(Config(wiki_root=tmp_path / "wiki"), cfg_path)
    loaded = load_config(cfg_path)
    assert loaded.full_sweep_every_n_runs == 60
    assert loaded.databases == []
    assert loaded.root_page_ids == []


def test_reads_legacy_singular_root_page_id(tmp_path: Path):
    """Configs written before multi-select stored a single `root_page_id`."""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[wiki]\nroot = "x"\n\n[notion]\nroot_page_id = "legacy1"\n', encoding="utf-8"
    )
    loaded = load_config(cfg_path)
    assert loaded.root_page_ids == ["legacy1"]
