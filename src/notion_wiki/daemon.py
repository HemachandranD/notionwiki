"""Optional long-lived pull loop (docs/design.md §10).

Strictly an alternative to the scheduled model (`notionwiki service install`,
schedule/) — for two cases only: sub-minute cadence below the OS scheduler's
floor, or co-hosting the `notionwiki graph` UI in one always-on process.
`apscheduler` is only ever imported here, behind the `[daemon]` extra.
"""

from __future__ import annotations

from pathlib import Path

from notion_wiki.config import Config
from notion_wiki.notion.client import NotionClient
from notion_wiki.paths import lock_path, state_db_path
from notion_wiki.store.db import StateDB


def tick_once(config: Config, token: str, state_dir: Path) -> None:
    """One pull cycle — the same thing a scheduled `notionwiki pull` invocation does."""
    from notion_wiki.ingest.pull import PullRunner

    client = NotionClient(token)
    db = StateDB(state_db_path(state_dir))
    try:
        runner = PullRunner(
            client,
            config.wiki_root,
            db,
            lock_path=lock_path(state_dir),
            state_dir=state_dir,
        )
        runner.run(databases=config.database_pairs())
    finally:
        db.close()
        client.close()


def run_forever(
    config: Config,
    token: str,
    state_dir: Path,
    *,
    interval_seconds: float,
    serve_graph: bool = False,
    graph_port: int = 7777,
) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: tick_once(config, token, state_dir), "interval", seconds=interval_seconds
    )

    if serve_graph:
        import threading

        from notion_wiki.graph.server import serve as serve_graph_ui

        thread = threading.Thread(
            target=serve_graph_ui,
            args=(config.wiki_root,),
            kwargs={"port": graph_port},
            daemon=True,
        )
        thread.start()

    scheduler.start()
