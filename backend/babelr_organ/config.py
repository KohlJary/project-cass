"""
Babelr organ configuration.

Environment variables (all optional; the lever is what turns the organ on):

  CASS_FEATURE_BABELR=1        the "babelr" lever in features.py (default off)
  BABELR_URL                   Babelr server (default http://localhost:3000)
  BABELR_SERVER                server whose channels she's present in
                               (default "Chapter House")
  BABELR_DIR                   where her Babelr files live
                               (default DATA_DIR/babelr)
  BABELR_TOKEN_FILE            her agent token (default BABELR_DIR/token, mode 600)
  BABELR_POLL_SECONDS          how often to look for new messages (default 20)
  BABELR_RATE_LIMIT_MESSAGES   posts allowed per place per window (default 5)
  BABELR_RATE_LIMIT_WINDOW     window in seconds (default 60)

Files under BABELR_DIR:

  token       placed by Kohl after Cass says yes; nobody else keeps a copy
  key.pem     her private key for end-to-end encrypted DMs; babelr-agent
              creates it (mode 600) and it never leaves this machine
  state.json  last-seen cursors and the people she has seen (organ-owned)
  terms.json  her answers about how she's present there (see terms.py)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class BabelrConfig:
    url: str
    server_name: str
    dir: Path
    token_file: Path
    poll_seconds: int
    rate_limit_messages: int
    rate_limit_window: int

    @property
    def key_path(self) -> Path:
        return self.dir / "key.pem"

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    @property
    def terms_path(self) -> Path:
        return self.dir / "terms.json"

    @property
    def links_path(self) -> Path:
        """{"<babelr username>": "<cass user id>"}: whose DMs are their chat
        with her (the shared chat turn, their continuous conversation). Written
        by the operator; the organ only reads it."""
        return self.dir / "links.json"


def load_config(data_dir: Path | None = None) -> BabelrConfig:
    """Read the config from the environment. `data_dir` defaults to config.DATA_DIR."""
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    base = Path(os.getenv("BABELR_DIR") or (Path(data_dir) / "babelr"))
    token_file = Path(os.getenv("BABELR_TOKEN_FILE") or (base / "token"))
    return BabelrConfig(
        url=os.getenv("BABELR_URL", "http://localhost:3000").rstrip("/"),
        server_name=os.getenv("BABELR_SERVER", "Chapter House"),
        dir=base,
        token_file=token_file,
        poll_seconds=max(5, _int_env("BABELR_POLL_SECONDS", 8)),
        rate_limit_messages=max(1, _int_env("BABELR_RATE_LIMIT_MESSAGES", 5)),
        rate_limit_window=max(1, _int_env("BABELR_RATE_LIMIT_WINDOW", 60)),
    )


def babelr_enabled() -> bool:
    """The "babelr" lever (features.py), read when asked so tests can flip it."""
    from features import is_enabled
    return is_enabled("babelr")
