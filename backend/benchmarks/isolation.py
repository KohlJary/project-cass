"""
Keep benchmark runs away from Cass's own data.

Every cell boots the app with DATA_DIR pointed at a fresh directory under the
run's scratch root. These guards refuse to go on when that isn't true:

- `check_data_dir(path)`: the directory must not be (or sit inside) the
  default data directory (backend/data, a symlink to <repo>/data on her
  machine), and must not already hold a cass.db, unless it is a cell's
  working copy of a sealed store (store.seed marks those).
- `check_checkout()`: some modules still build paths from their own file
  location instead of DATA_DIR (interviews, music, the wiki route, a legacy
  journal loop). Importing main_sdk creates directories there. So the app is
  only booted from a checkout whose backend/data is not her data: no symlink,
  and no cass.db in backend/data or <repo>/data. That is all it detects (a
  bind mount or a copy without cass.db would pass), so run from a git
  worktree or a clone, never from the live checkout.
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class IsolationError(RuntimeError):
    pass


def _live_data_dirs():
    dirs = {BACKEND_DIR / "data", REPO_DIR / "data"}
    out = set()
    for d in dirs:
        out.add(d.absolute())
        try:
            out.add(d.resolve())
        except OSError:
            pass
    return out


def check_data_dir(path) -> Path:
    """Refuse a DATA_DIR that is, or is inside, the default data directory."""
    p = Path(path).absolute()
    resolved = p.resolve()
    for live in _live_data_dirs():
        for candidate in (p, resolved):
            if candidate == live or live in candidate.parents:
                raise IsolationError(f"DATA_DIR {path} is inside the default data directory {live}; "
                                     "benchmarks only run against a fresh scratch directory")
    if (resolved / "cass.db").exists() and not (resolved / "STORE_COPY.json").exists():
        raise IsolationError(f"DATA_DIR {path} already holds a cass.db; benchmarks seed a fresh directory")
    return resolved


def check_checkout() -> None:
    """Refuse to boot the app from a checkout whose backend/data is real data."""
    link = BACKEND_DIR / "data"
    if link.is_symlink():
        raise IsolationError(
            f"{link} is a symlink (to {os.readlink(link)}). Some modules write under backend/data "
            "regardless of DATA_DIR, so run benchmarks from a git worktree or clone instead.")
    for d in (BACKEND_DIR / "data", REPO_DIR / "data"):
        if (d / "cass.db").exists():
            raise IsolationError(
                f"{d} holds a cass.db. Some modules write under backend/data regardless of DATA_DIR, "
                "so run benchmarks from a git worktree or clone instead.")


def check_env_data_dir() -> Path:
    """The current process's DATA_DIR env var must be set and isolated."""
    value = os.environ.get("DATA_DIR")
    if not value:
        raise IsolationError("DATA_DIR is not set; a benchmark process never uses the default data directory")
    return check_data_dir(value)
