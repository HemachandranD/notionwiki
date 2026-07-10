"""Archive helper: replaced/removed raw versions land here, never lost (docs/design.md §4, §5.3)."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def archive_file(src: Path, archive_dir: Path, slug: str, *, now: datetime | None = None) -> Path:
    """Copy `src` into `archive_dir` with a timestamped name.

    Caller decides afterward whether to overwrite `src` (update) or remove it
    (deletion) — archiving itself never touches the original.
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    timestamp = now.strftime("%Y-%m-%dT%H-%M")

    dest = archive_dir / f"{timestamp}_{slug}.md"
    suffix = 1
    while dest.exists():
        dest = archive_dir / f"{timestamp}_{slug}-{suffix}.md"
        suffix += 1

    shutil.copy2(src, dest)
    return dest
