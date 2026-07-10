from datetime import UTC, datetime

from notion_wiki.ingest.writer import (
    Outcome,
    SourceDocument,
    content_hash,
    decide_outcome,
    normalize_body,
)
from notion_wiki.store.db import PageRecord


def make_existing(**overrides) -> PageRecord:
    defaults = dict(
        notion_id="abc",
        title="Bridge Design",
        slug="bridge-design",
        filename="bridge-design.md",
        kind="page",
        content_hash=content_hash("body text"),
        remote_edited_at="2026-07-09T10:00:00.000Z",
        last_pulled="2026-07-09T10:00:05Z",
    )
    defaults.update(overrides)
    return PageRecord(**defaults)


def test_normalize_body_strips_trailing_whitespace_and_crlf():
    raw = "line one  \r\nline two\t\r\n\r\n\r\n"
    assert normalize_body(raw) == "line one\nline two\n"


def test_content_hash_ignores_frontmatter_churn():
    # Same body, hash must be stable regardless of anything outside body_markdown.
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello\n") == content_hash("hello")


def test_decide_outcome_new_when_no_existing_record():
    outcome = decide_outcome(
        None,
        new_hash="sha256:x",
        new_title="Title",
        remote_edited_at="2020-01-01T00:00:00.000Z",
        settle_window_minutes=5,
        now=datetime(2026, 7, 9, tzinfo=UTC),
    )
    assert outcome == Outcome.NEW


def test_decide_outcome_new_when_previously_deleted():
    existing = make_existing(deleted=True)
    outcome = decide_outcome(
        existing,
        new_hash="sha256:x",
        new_title="Title",
        remote_edited_at="2020-01-01T00:00:00.000Z",
        settle_window_minutes=5,
        now=datetime(2026, 7, 9, tzinfo=UTC),
    )
    assert outcome == Outcome.NEW


def test_decide_outcome_updated_when_hash_changes_outside_settle_window():
    existing = make_existing(remote_edited_at="2020-01-01T00:00:00.000Z")
    outcome = decide_outcome(
        existing,
        new_hash="sha256:different",
        new_title="Bridge Design",
        remote_edited_at="2020-01-01T00:05:00.000Z",
        settle_window_minutes=5,
        now=datetime(2026, 7, 9, tzinfo=UTC),
    )
    assert outcome == Outcome.UPDATED


def test_decide_outcome_unchanged():
    existing_hash = content_hash("same body")
    existing = make_existing(
        content_hash=existing_hash, remote_edited_at="2020-01-01T00:00:00.000Z"
    )
    outcome = decide_outcome(
        existing,
        new_hash=existing_hash,
        new_title="Bridge Design",
        remote_edited_at="2020-01-01T00:00:00.000Z",
        settle_window_minutes=5,
        now=datetime(2026, 7, 9, tzinfo=UTC),
    )
    assert outcome == Outcome.UNCHANGED


def test_decide_outcome_renamed_when_only_title_changes():
    existing_hash = content_hash("same body")
    existing = make_existing(
        content_hash=existing_hash, remote_edited_at="2020-01-01T00:00:00.000Z"
    )
    outcome = decide_outcome(
        existing,
        new_hash=existing_hash,
        new_title="New Title",
        remote_edited_at="2020-01-01T00:00:00.000Z",
        settle_window_minutes=5,
        now=datetime(2026, 7, 9, tzinfo=UTC),
    )
    assert outcome == Outcome.RENAMED


def test_decide_outcome_settling_while_timestamp_still_advancing():
    now = datetime(2026, 7, 9, 14, 3, 0, tzinfo=UTC)
    existing = make_existing(remote_edited_at="2026-07-09T14:00:00.000Z", settling_since=None)
    outcome = decide_outcome(
        existing,
        new_hash="sha256:changed",
        new_title="Bridge Design",
        remote_edited_at="2026-07-09T14:02:00.000Z",  # within the 5-minute settle window
        settle_window_minutes=5,
        now=now,
    )
    assert outcome == Outcome.SETTLING


def test_decide_outcome_writes_once_timestamp_stabilizes():
    now = datetime(2026, 7, 9, 14, 3, 0, tzinfo=UTC)
    # settling_since records the timestamp we observed (but didn't write) last tick;
    # this tick sees the *same* timestamp, meaning editing stopped.
    existing = make_existing(
        remote_edited_at="2026-07-09T13:50:00.000Z", settling_since="2026-07-09T14:02:00.000Z"
    )
    outcome = decide_outcome(
        existing,
        new_hash="sha256:changed",
        new_title="Bridge Design",
        remote_edited_at="2026-07-09T14:02:00.000Z",
        settle_window_minutes=5,
        now=now,
    )
    assert outcome == Outcome.UPDATED


def test_source_document_frontmatter_key_order_and_content():
    doc = SourceDocument(
        notion_id="1a2b3c4d",
        notion_url="https://notion.so/x",
        kind="database_row",
        title="Row 4",
        body_markdown="hello",
        parent_id="9f8e7d6c",
        breadcrumb=["Home", "Projects"],
        database_name="Reading Notes",
        remote_edited_at="2026-07-09T14:01:00Z",
        last_pulled="2026-07-09T14:03:11Z",
    )
    rendered = doc.render()
    assert rendered.startswith("---\n")
    assert "notion_id: 1a2b3c4d" in rendered
    assert "kind: database_row" in rendered
    assert "database: Reading Notes" in rendered
    assert "title: Row 4" in rendered
    assert "# Row 4" in rendered
    assert rendered.endswith("hello\n")

    keys_in_order = [
        line.split(":")[0]
        for line in rendered.split("---")[1].strip().splitlines()
        if not line.startswith(" ") and not line.startswith("-")
    ]
    assert keys_in_order.index("notion_id") < keys_in_order.index("content_hash")
    assert keys_in_order.index("kind") < keys_in_order.index("database")
