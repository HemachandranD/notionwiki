"""notionwiki: one-way ingestion bridge from Notion into an LLM Wiki's raw layer."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("notionwiki")
except PackageNotFoundError:
    # Editable/uninstalled checkout (e.g. running straight from a source tree
    # without `pip install -e .`) — no package metadata to read.
    __version__ = "0.0.0+dev"
