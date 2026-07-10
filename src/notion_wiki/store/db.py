"""SQLite ingestion state (docs/design.md §3, §5.1, §5.3).

Tracks per-page bookkeeping (`pages`), run history for the single-instance
lock/skip ledger (`runs`), and small scalars like the incremental baseline
and last-full-sweep time (`meta`). This is the only ingestion state that
persists between runs — everything else is recomputed each pull.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    notion_id       TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    slug            TEXT NOT NULL,
    filename        TEXT NOT NULL,
    kind            TEXT NOT NULL,   -- page | database_row
    database_id     TEXT,
    database_name   TEXT,
    parent_id       TEXT,
    breadcrumb_json TEXT,
    content_hash    TEXT,
    remote_edited_at TEXT,
    last_pulled     TEXT,
    settling_since  TEXT,
    deleted         INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pages_slug ON pages(slug);

CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    mode         TEXT NOT NULL,   -- incremental | full
    status       TEXT NOT NULL    -- running | ok | error | skipped
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


@dataclass
class PageRecord:
    notion_id: str
    title: str
    slug: str
    filename: str
    kind: str  # "page" | "database_row"
    content_hash: str | None = None
    remote_edited_at: str | None = None
    last_pulled: str | None = None
    database_id: str | None = None
    database_name: str | None = None
    parent_id: str | None = None
    breadcrumb_json: str | None = None
    settling_since: str | None = None
    deleted: bool = False

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PageRecord:
        return cls(
            notion_id=row["notion_id"],
            title=row["title"],
            slug=row["slug"],
            filename=row["filename"],
            kind=row["kind"],
            content_hash=row["content_hash"],
            remote_edited_at=row["remote_edited_at"],
            last_pulled=row["last_pulled"],
            database_id=row["database_id"],
            database_name=row["database_name"],
            parent_id=row["parent_id"],
            breadcrumb_json=row["breadcrumb_json"],
            settling_since=row["settling_since"],
            deleted=bool(row["deleted"]),
        )


class StateDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> StateDB:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- pages ---

    def get_page(self, notion_id: str) -> PageRecord | None:
        row = self._conn.execute("SELECT * FROM pages WHERE notion_id = ?", (notion_id,)).fetchone()
        return PageRecord.from_row(row) if row else None

    def get_page_by_slug(self, slug: str) -> PageRecord | None:
        row = self._conn.execute("SELECT * FROM pages WHERE slug = ?", (slug,)).fetchone()
        return PageRecord.from_row(row) if row else None

    def slug_taken(self, slug: str) -> bool:
        return self.get_page_by_slug(slug) is not None

    def upsert_page(self, record: PageRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO pages (
                notion_id, title, slug, filename, kind, database_id, database_name,
                parent_id, breadcrumb_json, content_hash, remote_edited_at,
                last_pulled, settling_since, deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(notion_id) DO UPDATE SET
                title=excluded.title,
                slug=excluded.slug,
                filename=excluded.filename,
                kind=excluded.kind,
                database_id=excluded.database_id,
                database_name=excluded.database_name,
                parent_id=excluded.parent_id,
                breadcrumb_json=excluded.breadcrumb_json,
                content_hash=excluded.content_hash,
                remote_edited_at=excluded.remote_edited_at,
                last_pulled=excluded.last_pulled,
                settling_since=excluded.settling_since,
                deleted=excluded.deleted
            """,
            (
                record.notion_id,
                record.title,
                record.slug,
                record.filename,
                record.kind,
                record.database_id,
                record.database_name,
                record.parent_id,
                record.breadcrumb_json,
                record.content_hash,
                record.remote_edited_at,
                record.last_pulled,
                record.settling_since,
                int(record.deleted),
            ),
        )
        self._conn.commit()

    def mark_deleted(self, notion_id: str) -> None:
        self._conn.execute("UPDATE pages SET deleted = 1 WHERE notion_id = ?", (notion_id,))
        self._conn.commit()

    def active_notion_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT notion_id FROM pages WHERE deleted = 0").fetchall()
        return {row["notion_id"] for row in rows}

    def resolve_slug(self, notion_id: str) -> str | None:
        """Return "raw/notion/<slug>" for a known, non-deleted page — used to resolve
        page-mention links during conversion (docs/design.md §5.2)."""
        record = self.get_page(notion_id)
        if record is None or record.deleted:
            return None
        return f"raw/notion/{record.slug}"

    def all_pages(self) -> list[PageRecord]:
        rows = self._conn.execute("SELECT * FROM pages ORDER BY notion_id").fetchall()
        return [PageRecord.from_row(row) for row in rows]

    # --- meta ---

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    # --- runs ---

    def start_run(self, mode: str, started_at: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO runs (started_at, mode, status) VALUES (?, ?, 'running')",
            (started_at, mode),
        )
        self._conn.commit()
        return cursor.lastrowid

    def finish_run(self, run_id: int, status: str, finished_at: str) -> None:
        self._conn.execute(
            "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
            (status, finished_at, run_id),
        )
        self._conn.commit()

    def recent_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
