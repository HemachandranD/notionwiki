"""Notion integration token storage (docs/design.md §11).

Stored in the OS keyring, never in config.toml. NOTION_WIKI_TOKEN is a
headless-friendly override (also the recommended path when a Linux box's
Secret Service backend is unavailable — see schedule/linux.py).
"""

from __future__ import annotations

import keyring

SERVICE_NAME = "notionwiki"
KEY_NAME = "notion_token"
ENV_VAR = "NOTION_WIKI_TOKEN"


def get_token() -> str | None:
    import os

    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return env_value
    return keyring.get_password(SERVICE_NAME, KEY_NAME)


def set_token(token: str) -> None:
    keyring.set_password(SERVICE_NAME, KEY_NAME, token)


def delete_token() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, KEY_NAME)
    except keyring.errors.PasswordDeleteError:
        pass
