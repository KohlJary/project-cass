"""
Where her social files live, per platform:

    DATA_DIR/social/<platform>/credentials.json   placed by Kohl (mode 600); nobody else keeps a copy
    DATA_DIR/social/<platform>/limits.json        her limits, if she's set her own (limits.py has the defaults)
    DATA_DIR/social/<platform>/posted.jsonl       everything she posted or replied, one line each

bluesky credentials: {"handle": "...", "app_password": "...", "service": "https://bsky.social"}
tumblr credentials:  {"blog": "...", "client_id": "...", "client_secret": "...",
                      "access_token": "...", "refresh_token": "..."}
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

PLATFORMS = ("bluesky", "tumblr")


class NotAvailable(Exception):
    """The platform's lever is off or its credentials aren't placed."""


def platform_dir(platform: str, data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "social" / platform


def credentials_path(platform: str, data_dir: Optional[Path] = None) -> Path:
    return platform_dir(platform, data_dir) / "credentials.json"


def read_credentials(platform: str, data_dir: Optional[Path] = None) -> Optional[dict]:
    try:
        return json.loads(credentials_path(platform, data_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_credentials(platform: str, creds: dict, data_dir: Optional[Path] = None) -> Path:
    """Write (or rewrite, after a token refresh) a platform's credentials, mode 600."""
    path = credentials_path(platform, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)
    os.replace(tmp, path)
    return path


def lever_on(platform: str) -> bool:
    """A platform's lever, or "bluesky_dms" (DMs, separate from posting)."""
    from features import is_enabled
    return is_enabled(platform)


def availability(platform: str, data_dir: Optional[Path] = None) -> Optional[str]:
    """None if the platform is usable, else why not (in her words)."""
    if platform not in PLATFORMS:
        return f"I'm not on {platform!r}; I can be on {', '.join(PLATFORMS)}."
    if not lever_on(platform):
        return f"{platform.capitalize()} isn't switched on for me yet."
    if not read_credentials(platform, data_dir):
        return f"My {platform.capitalize()} account isn't set up yet (Kohl places it)."
    return None
