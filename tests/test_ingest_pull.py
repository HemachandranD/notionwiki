from datetime import UTC, datetime
from pathlib import Path

from notion_wiki.ingest.pull import PullRunner
from notion_wiki.store.db import StateDB
from notion_wiki.store.lock import SingleInstanceLock
from tests.fakes import FakeNotionClient, make_raw_page, paragraph_block


def make_runner(tmp_path: Path, client: FakeNotionClient) -> tuple[PullRunner, Path, Path]:
    wiki_root = tmp_path / "wiki"
    state_dir = tmp_path / "state"
    db = StateDB(state_dir / "state.db")
    runner = PullRunner(
        client,
        wiki_root,
        db,
        lock_path=state_dir / "pull.lock",
        state_dir=state_dir,
    )
    return runner, wiki_root, state_dir


def test_new_page_is_written_and_logged(tmp_path: Path):
    client = FakeNotionClient(
        pages=[make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("hello world")]},
    )
    runner, wiki_root, _ = make_runner(tmp_path, client)

    stats = runner.run(now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC))

    assert stats.new == 1
    dest = wiki_root / "raw" / "notion" / "bridge-design.md"
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "notion_id: p1" in content
    assert "# Bridge Design" in content
    assert "hello world" in content

    entries = runner.log.read_entries()
    assert len(entries) == 1
    assert entries[0].outcome == "new"
    assert entries[0].notion_id == "p1"

    record = runner.db.get_page("p1")
    assert record.slug == "bridge-design"


def test_unchanged_page_is_not_rewritten_or_logged(tmp_path: Path):
    page = make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T14:00:00.000Z")
    client = FakeNotionClient(pages=[page], blocks={"p1": [paragraph_block("hello world")]})
    runner, wiki_root, _ = make_runner(tmp_path, client)
    runner.run(now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC))

    dest = wiki_root / "raw" / "notion" / "bridge-design.md"
    mtime_before = dest.stat().st_mtime

    stats = runner.run(now=datetime(2026, 7, 9, 14, 4, tzinfo=UTC))

    assert stats.unchanged == 1
    assert dest.stat().st_mtime == mtime_before
    entries = runner.log.read_entries()
    assert len(entries) == 1  # only the original "new" entry; unchanged isn't logged


def test_updated_page_archives_prior_version(tmp_path: Path):
    client = FakeNotionClient(
        pages=[make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("version one")]},
    )
    runner, wiki_root, state_dir = make_runner(tmp_path, client)
    runner.run(now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC))

    # Simulate an edit far outside the settle window with new content.
    client.pages = [
        make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T15:00:00.000Z")
    ]
    client.blocks["p1"] = [paragraph_block("version two")]

    stats = runner.run(now=datetime(2026, 7, 9, 15, 30, tzinfo=UTC))

    assert stats.updated == 1
    dest = wiki_root / "raw" / "notion" / "bridge-design.md"
    assert "version two" in dest.read_text(encoding="utf-8")

    archive_dir = state_dir / "archive"
    archived_files = list(archive_dir.glob("*bridge-design*"))
    assert len(archived_files) == 1
    assert "version one" in archived_files[0].read_text(encoding="utf-8")

    entries = runner.log.read_entries()
    assert entries[-1].outcome == "updated"
    assert any("archived→" in d for d in entries[-1].details)


def test_renamed_page_keeps_filename_but_updates_title(tmp_path: Path):
    client = FakeNotionClient(
        pages=[make_raw_page("p1", "Design Doc", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("same body")]},
    )
    runner, wiki_root, _ = make_runner(tmp_path, client)
    runner.run(now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC))

    client.pages = [
        make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T15:00:00.000Z")
    ]
    # blocks unchanged -> same content hash, only the title differs

    stats = runner.run(now=datetime(2026, 7, 9, 15, 30, tzinfo=UTC))

    assert stats.renamed == 1
    dest = wiki_root / "raw" / "notion" / "design-doc.md"
    assert dest.exists()  # frozen filename, never renamed (§4)
    assert not (wiki_root / "raw" / "notion" / "bridge-design.md").exists()

    record = runner.db.get_page("p1")
    assert record.title == "Bridge Design"
    assert record.slug == "design-doc"

    entries = runner.log.read_entries()
    assert entries[-1].outcome == "renamed"
    assert "Bridge Design (was: Design Doc)" == entries[-1].title


def test_settle_window_holds_off_then_writes_once_stable(tmp_path: Path):
    client = FakeNotionClient(
        pages=[make_raw_page("p1", "Live Doc", last_edited_time="2026-07-09T13:00:00.000Z")],
        blocks={"p1": [paragraph_block("v1")]},
    )
    runner, wiki_root, _ = make_runner(tmp_path, client)
    runner.run(now=datetime(2026, 7, 9, 13, 3, tzinfo=UTC))
    dest = wiki_root / "raw" / "notion" / "live-doc.md"
    assert "v1" in dest.read_text(encoding="utf-8")

    # Edit happens right now (well within the 5-minute settle window).
    client.pages = [make_raw_page("p1", "Live Doc", last_edited_time="2026-07-09T14:00:00.000Z")]
    client.blocks["p1"] = [paragraph_block("v2 mid-edit")]
    now_tick1 = datetime(2026, 7, 9, 14, 0, 30, tzinfo=UTC)
    stats1 = runner.run(now=now_tick1)

    assert stats1.settling == 1
    assert "v1" in dest.read_text(encoding="utf-8")  # not written yet

    # Next tick: timestamp unchanged from what we last observed -> editing stopped.
    now_tick2 = datetime(2026, 7, 9, 14, 1, 0, tzinfo=UTC)
    stats2 = runner.run(now=now_tick2)

    assert stats2.updated == 1
    assert "v2 mid-edit" in dest.read_text(encoding="utf-8")


def test_full_sweep_archives_deleted_pages(tmp_path: Path):
    client = FakeNotionClient(
        pages=[make_raw_page("p1", "Keeper", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("keep me")]},
    )
    runner, wiki_root, state_dir = make_runner(tmp_path, client)
    runner.run(full=True, now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC))

    client.pages = []  # p1 no longer appears -> deleted in Notion

    stats = runner.run(full=True, now=datetime(2026, 7, 9, 15, 3, tzinfo=UTC))

    assert stats.archived == 1
    assert not (wiki_root / "raw" / "notion" / "keeper.md").exists()
    archived_files = list((state_dir / "archive").glob("*keeper*"))
    assert len(archived_files) == 1

    record = runner.db.get_page("p1")
    assert record.deleted is True

    entries = runner.log.read_entries()
    assert entries[-1].outcome == "archived"
    assert "deleted in Notion" in entries[-1].details


def test_database_rows_become_individual_pages(tmp_path: Path):
    row1 = make_raw_page(
        "row1",
        "Row One",
        parent={"type": "database_id", "database_id": "db1"},
        last_edited_time="2026-07-09T14:00:00.000Z",
        properties={"Status": {"type": "select", "select": {"name": "Done"}}},
    )
    row2 = make_raw_page(
        "row2",
        "Row Two",
        parent={"type": "database_id", "database_id": "db1"},
        last_edited_time="2026-07-09T14:00:00.000Z",
    )
    client = FakeNotionClient(
        pages=[],
        blocks={
            "row1": [paragraph_block("row one body")],
            "row2": [paragraph_block("row two body")],
        },
        databases={"db1": [row1, row2]},
    )
    runner, wiki_root, _ = make_runner(tmp_path, client)

    stats = runner.run(
        databases=[("db1", "Reading Notes")], now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC)
    )

    assert stats.new == 2
    row_one_path = wiki_root / "raw" / "notion" / "row-one.md"
    content = row_one_path.read_text(encoding="utf-8")
    assert "kind: database_row" in content
    assert "database: Reading Notes" in content
    assert "| Status | Done |" in content
    assert "row one body" in content

    record = runner.db.get_page("row1")
    assert record.kind == "database_row"
    assert record.database_name == "Reading Notes"


def test_lock_contention_skips_and_logs(tmp_path: Path):
    client = FakeNotionClient(pages=[])
    runner, wiki_root, state_dir = make_runner(tmp_path, client)

    held_lock = SingleInstanceLock(state_dir / "pull.lock")
    held_lock.acquire()
    try:
        stats = runner.run(now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC))
    finally:
        held_lock.release()

    assert stats.skipped is True
    entries = runner.log.read_entries()
    assert entries[-1].action == "run"
    assert entries[-1].outcome == "skipped"
    assert entries[-1].notion_id == "-"


def test_mention_link_resolves_once_target_known(tmp_path: Path):

    mention_run = {
        "plain_text": "Other Page",
        "type": "mention",
        "mention": {"type": "page", "page": {"id": "p2"}},
        "annotations": {},
        "href": None,
    }
    from notion_wiki.notion.models import Block

    mentioning_block = Block(
        id="m1", type="paragraph", has_children=False, data={"rich_text": [mention_run]}
    )
    client = FakeNotionClient(
        pages=[
            make_raw_page("p2", "Other Page", last_edited_time="2026-07-09T13:00:00.000Z"),
            make_raw_page("p1", "Main Page", last_edited_time="2026-07-09T14:00:00.000Z"),
        ],
        blocks={"p2": [paragraph_block("other content", "b2")], "p1": [mentioning_block]},
    )
    runner, wiki_root, _ = make_runner(tmp_path, client)

    runner.run(now=datetime(2026, 7, 9, 14, 3, tzinfo=UTC))

    main_content = (wiki_root / "raw" / "notion" / "main-page.md").read_text(encoding="utf-8")
    assert "[[raw/notion/other-page]]" in main_content
