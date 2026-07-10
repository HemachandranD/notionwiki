"""Asset download (docs/design.md §5.2, §14.1).

Notion's file/image URLs are pre-signed S3 links that expire in about an
hour, so the download must happen inside the same pull run that discovers
the reference — never deferred to a later tick. Filenames are the content
hash of the downloaded bytes: this dedupes identical images reused across
pages and sidesteps churn from Notion's rotating asset URLs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

_CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "application/pdf": ".pdf",
}


def _guess_extension(url: str, content_type: str | None) -> str:
    name = Path(urlparse(url).path).name
    if "." in name:
        return Path(name).suffix
    return _CONTENT_TYPE_EXT.get((content_type or "").split(";")[0].strip(), "")


def download_asset(url: str, assets_dir: Path, *, http_client: httpx.Client | None = None) -> str:
    """Download `url` into `assets_dir`, named by content hash.

    Returns the path relative to the feeder dir, e.g. "assets/sha256-<hash>.png".
    Already-present files (same hash) are not re-downloaded.
    """
    client = http_client or httpx.Client(timeout=30.0, follow_redirects=True)
    owns_client = http_client is None
    try:
        response = client.get(url)
        response.raise_for_status()
        content = response.content
        content_type = response.headers.get("content-type")
    finally:
        if owns_client:
            client.close()

    digest = hashlib.sha256(content).hexdigest()
    filename = f"sha256-{digest}{_guess_extension(url, content_type)}"
    assets_dir.mkdir(parents=True, exist_ok=True)
    dest = assets_dir / filename
    if not dest.exists():
        dest.write_bytes(content)
    return f"assets/{filename}"
