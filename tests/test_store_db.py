from pathlib import Path

from notion_wiki.store.db import PageRecord, StateDB


def make_record(**overrides) -> PageRecord:
    defaults = dict(
        notion_id="abc123",
        title="Bridge Design",
        slug="bridge-design",
        filename="bridge-design.md",
        kind="page",
        content_hash="sha256:deadbeef",
        remote_edited_at="2026-07-09T14:01:00Z",
        last_pulled="2026-07-09T14:03:11Z",
    )
    defaults.update(overrides)
    return PageRecord(**defaults)


def test_upsert_and_get(tmp_path: Path):
    db = StateDB(tmp_path / "state.db")
    db.upsert_page(make_record())

    fetched = db.get_page("abc123")
    assert fetched is not None
    assert fetched.title == "Bridge Design"
    assert fetched.slug == "bridge-design"
    assert fetched.deleted is False


def test_upsert_updates_existing_row(tmp_path: Path):
    db = StateDB(tmp_path / "state.db")
    db.upsert_page(make_record())
    db.upsert_page(make_record(title="Bridge Design (renamed)", content_hash="sha256:cafebabe"))

    fetched = db.get_page("abc123")
    assert fetched.title == "Bridge Design (renamed)"
    assert fetched.content_hash == "sha256:cafebabe"
    assert len(db.all_pages()) == 1


def test_get_page_by_slug(tmp_path: Path):
    db = StateDB(tmp_path / "state.db")
    db.upsert_page(make_record())
    assert db.get_page_by_slug("bridge-design").notion_id == "abc123"
    assert db.get_page_by_slug("missing") is None
    assert db.slug_taken("bridge-design") is True
    assert db.slug_taken("missing") is False


def test_mark_deleted_excludes_from_active_ids(tmp_path: Path):
    db = StateDB(tmp_path / "state.db")
    db.upsert_page(make_record())
    db.upsert_page(make_record(notion_id="def456", slug="other-page", filename="other-page.md"))

    assert db.active_notion_ids() == {"abc123", "def456"}
    db.mark_deleted("abc123")
    assert db.active_notion_ids() == {"def456"}


def test_resolve_slug_returns_none_for_deleted_or_unknown(tmp_path: Path):
    db = StateDB(tmp_path / "state.db")
    db.upsert_page(make_record())
    assert db.resolve_slug("abc123") == "raw/notion/bridge-design"
    assert db.resolve_slug("unknown") is None

    db.mark_deleted("abc123")
    assert db.resolve_slug("abc123") is None


def test_meta_roundtrip(tmp_path: Path):
    db = StateDB(tmp_path / "state.db")
    assert db.get_meta("last_full_sweep_at") is None
    db.set_meta("last_full_sweep_at", "2026-07-09T14:00:00Z")
    assert db.get_meta("last_full_sweep_at") == "2026-07-09T14:00:00Z"
    db.set_meta("last_full_sweep_at", "2026-07-09T15:00:00Z")
    assert db.get_meta("last_full_sweep_at") == "2026-07-09T15:00:00Z"


def test_run_lifecycle(tmp_path: Path):
    db = StateDB(tmp_path / "state.db")
    run_id = db.start_run("incremental", "2026-07-09T14:03:00Z")
    db.finish_run(run_id, "ok", "2026-07-09T14:03:05Z")

    runs = db.recent_runs()
    assert len(runs) == 1
    assert runs[0]["mode"] == "incremental"
    assert runs[0]["status"] == "ok"


def test_reopening_db_persists_data(tmp_path: Path):
    path = tmp_path / "state.db"
    db1 = StateDB(path)
    db1.upsert_page(make_record())
    db1.close()

    db2 = StateDB(path)
    assert db2.get_page("abc123") is not None
