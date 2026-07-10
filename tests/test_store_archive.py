from datetime import datetime
from pathlib import Path

from notion_wiki.store.archive import archive_file


def test_archive_copies_with_timestamped_name(tmp_path: Path):
    src = tmp_path / "raw" / "bridge-design.md"
    src.parent.mkdir(parents=True)
    src.write_text("---\nnotion_id: abc\n---\n\n# Bridge Design\n", encoding="utf-8")

    archive_dir = tmp_path / "archive"
    dest = archive_file(src, archive_dir, "bridge-design", now=datetime(2026, 7, 9, 14, 3))

    assert dest.name == "2026-07-09T14-03_bridge-design.md"
    assert dest.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    assert src.exists()  # archiving copies; caller decides whether to remove the original


def test_archive_collision_gets_suffix(tmp_path: Path):
    src = tmp_path / "raw" / "page.md"
    src.parent.mkdir(parents=True)
    src.write_text("v1", encoding="utf-8")
    archive_dir = tmp_path / "archive"
    ts = datetime(2026, 7, 9, 14, 3)

    dest1 = archive_file(src, archive_dir, "page", now=ts)
    src.write_text("v2", encoding="utf-8")
    dest2 = archive_file(src, archive_dir, "page", now=ts)

    assert dest1.name == "2026-07-09T14-03_page.md"
    assert dest2.name == "2026-07-09T14-03_page-1.md"
    assert dest1.read_text(encoding="utf-8") == "v1"
    assert dest2.read_text(encoding="utf-8") == "v2"
