"""config.toml read/write (docs/design.md §4, §8.1).

The Notion integration token is never stored here (§11) — it lives in the OS
keyring, with a NOTION_WIKI_TOKEN env-var override for headless setups.

Database scope (§14.2, open question) is resolved once at `init` time: the
wizard's all/choose prompt is snapshotted into an explicit `[[notion.databases]]`
list of {id, name} pairs, rather than storing a live "all" that would need
re-resolving via the API on every pull.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from notion_wiki.paths import config_path


@dataclass
class DatabaseRef:
    id: str
    name: str


@dataclass
class Config:
    wiki_root: Path
    root_page_id: str = ""
    databases: list[DatabaseRef] = field(default_factory=list)
    interval_minutes: int = 1
    full_sweep_every_n_runs: int = 60  # ~hourly at a 1-minute cadence (§5.1)

    def database_pairs(self) -> list[tuple[str, str]]:
        return [(db.id, db.name) for db in self.databases]

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        wiki = data.get("wiki", {})
        notion = data.get("notion", {})
        schedule = data.get("schedule", {})
        return cls(
            wiki_root=Path(wiki["root"]).expanduser(),
            root_page_id=notion.get("root_page_id", ""),
            databases=[DatabaseRef(**db) for db in notion.get("databases", [])],
            interval_minutes=schedule.get("interval_minutes", 1),
            full_sweep_every_n_runs=schedule.get("full_sweep_every_n_runs", 60),
        )

    def to_dict(self) -> dict:
        return {
            "wiki": {"root": str(self.wiki_root)},
            "notion": {
                "root_page_id": self.root_page_id,
                "databases": [{"id": db.id, "name": db.name} for db in self.databases],
            },
            "schedule": {
                "interval_minutes": self.interval_minutes,
                "full_sweep_every_n_runs": self.full_sweep_every_n_runs,
            },
        }


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config.from_dict(data)


def save_config(config: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(config.to_dict(), f)


def config_exists(path: Path | None = None) -> bool:
    path = path or config_path()
    return path.exists()
