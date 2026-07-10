from datetime import UTC, datetime, timedelta

from notion_wiki.cli import _banner_suppressed, _humanize_age


def test_banner_suppressed_by_json_flag():
    assert _banner_suppressed(["pull", "--json"]) is True


def test_banner_suppressed_by_quiet_flag():
    assert _banner_suppressed(["pull", "--quiet"]) is True
    assert _banner_suppressed(["pull", "-q"]) is True


def test_banner_not_suppressed_for_plain_args(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert _banner_suppressed(["init"]) is False


def test_banner_suppressed_when_not_a_tty(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert _banner_suppressed([]) is True


def test_humanize_age_never():
    assert _humanize_age(None) == "never"


def test_humanize_age_buckets():
    now = datetime.now(UTC)
    assert _humanize_age((now - timedelta(seconds=30)).isoformat()) == "just now"
    assert _humanize_age((now - timedelta(minutes=5)).isoformat()) == "5m ago"
    assert _humanize_age((now - timedelta(hours=3)).isoformat()) == "3h ago"
    assert _humanize_age((now - timedelta(days=2)).isoformat()) == "2d ago"
