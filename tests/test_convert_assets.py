import hashlib
from pathlib import Path

import httpx
import respx

from notion_wiki.convert.assets import download_asset


@respx.mock
def test_download_asset_names_by_content_hash(tmp_path: Path):
    content = b"fake-png-bytes"
    respx.get("https://s3.example.com/signed/foo.png").mock(
        return_value=httpx.Response(200, content=content, headers={"content-type": "image/png"})
    )
    assets_dir = tmp_path / "assets"

    rel_path = download_asset("https://s3.example.com/signed/foo.png", assets_dir)

    digest = hashlib.sha256(content).hexdigest()
    assert rel_path == f"assets/sha256-{digest}.png"
    assert (assets_dir / f"sha256-{digest}.png").read_bytes() == content


@respx.mock
def test_download_asset_dedupes_identical_content(tmp_path: Path):
    content = b"same-bytes"
    respx.get("https://s3.example.com/a.png").mock(
        return_value=httpx.Response(200, content=content, headers={"content-type": "image/png"})
    )
    respx.get("https://s3.example.com/b-rotated-url.png").mock(
        return_value=httpx.Response(200, content=content, headers={"content-type": "image/png"})
    )
    assets_dir = tmp_path / "assets"

    path1 = download_asset("https://s3.example.com/a.png", assets_dir)
    path2 = download_asset("https://s3.example.com/b-rotated-url.png", assets_dir)

    assert path1 == path2
    assert len(list(assets_dir.iterdir())) == 1


def test_download_asset_leaves_non_http_urls_untouched(tmp_path: Path):
    """Empty/relative/data/internal references must not crash the pull — they are
    returned unchanged with no network call (no respx mock needed)."""
    assets_dir = tmp_path / "assets"
    for ref in ("", "/relative/path.png", "data:image/png;base64,AAAA", "notion://page/x"):
        assert download_asset(ref, assets_dir) == ref
    assert not assets_dir.exists()


@respx.mock
def test_download_asset_falls_back_to_content_type_extension(tmp_path: Path):
    content = b"gif-bytes"
    respx.get("https://s3.example.com/signed-no-ext").mock(
        return_value=httpx.Response(200, content=content, headers={"content-type": "image/gif"})
    )
    assets_dir = tmp_path / "assets"

    rel_path = download_asset("https://s3.example.com/signed-no-ext", assets_dir)

    assert rel_path.endswith(".gif")
