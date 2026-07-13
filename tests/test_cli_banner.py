import io
from datetime import UTC, datetime, timedelta

from notion_wiki.cli import _banner_suppressed, _force_utf8_output, _humanize_age


def test_force_utf8_output_survives_legacy_cp1252_stream(monkeypatch):
    """A Windows console defaulting to cp1252 cannot encode the ✓ glyphs in our
    output; _force_utf8_output must reconfigure the stream so printing them does
    not raise UnicodeEncodeError (regression: `notionwiki pull` aborting on \\u2713)."""
    legacy = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr("sys.stdout", legacy)
    _force_utf8_output()
    legacy.write("✓ pull complete")  # would raise under cp1252 without reconfigure
    legacy.flush()
    assert legacy.buffer.getvalue().decode("utf-8") == "✓ pull complete"


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
