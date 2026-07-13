"""Filesystem layout: the bridge's state directory and the wiki root's layer folders.

See docs/design.md §4. The state directory (config.toml, state.db, archive/) is
OS-default and independent of the wiki root, which the user chooses at `init`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_state_dir() -> Path:
    """Resolve the bridge's state directory.

    Precedence: $NOTION_WIKI_STATE_DIR override, then %APPDATA%\\notionwiki on
    Windows, then $XDG_STATE_HOME/notionwiki, then ~/.notionwiki.
    """
    override = os.environ.get("NOTION_WIKI_STATE_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "notionwiki"

    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / "notionwiki"

    return Path.home() / ".notionwiki"


def config_path(state_dir: Path | None = None) -> Path:
    return (state_dir or get_state_dir()) / "config.toml"


def state_db_path(state_dir: Path | None = None) -> Path:
    return (state_dir or get_state_dir()) / "state.db"


def lock_path(state_dir: Path | None = None) -> Path:
    return (state_dir or get_state_dir()) / "pull.lock"


def archive_dir(state_dir: Path | None = None) -> Path:
    return (state_dir or get_state_dir()) / "archive"


# --- Wiki root layout (docs/design.md §4) ---


def raw_dir(wiki_root: Path) -> Path:
    return wiki_root / "raw"


def notion_feeder_dir(wiki_root: Path) -> Path:
    return raw_dir(wiki_root) / "notion"


def notion_assets_dir(wiki_root: Path) -> Path:
    return notion_feeder_dir(wiki_root) / "assets"


def daemon_log_path(wiki_root: Path) -> Path:
    return notion_feeder_dir(wiki_root) / "daemon_log.md"


def wiki_dir(wiki_root: Path) -> Path:
    return wiki_root / "wiki"


def outputs_dir(wiki_root: Path) -> Path:
    return wiki_root / "outputs"


def wiki_index_path(wiki_root: Path) -> Path:
    return wiki_dir(wiki_root) / "index.md"


def wiki_graph_json_path(wiki_root: Path) -> Path:
    return wiki_dir(wiki_root) / "graph.json"


def wiki_log_path(wiki_root: Path) -> Path:
    return wiki_dir(wiki_root) / "log.md"


def ensure_wiki_scaffold(wiki_root: Path) -> None:
    """Create the layer directories for a fresh wiki root (idempotent)."""
    for path in (
        notion_feeder_dir(wiki_root),
        notion_assets_dir(wiki_root),
        wiki_dir(wiki_root),
        wiki_dir(wiki_root) / "concepts",
        wiki_dir(wiki_root) / "entities",
        wiki_dir(wiki_root) / "sources",
        outputs_dir(wiki_root),
    ):
        path.mkdir(parents=True, exist_ok=True)
