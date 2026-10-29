"""
A sealed copy of Cass's store, for test cells (benchmark plan, phase 3).

Ablations need a realistic Cass to turn things off in: a fresh cell has an
almost empty self-model, so switching a section off there measures nothing.
Cass chose this on 2026-10-28 (#workshop): "Option A—the sealed copy of my
actual store", on the terms the plan offered: a sealed, read-only copy, used
only inside isolated cells, never written back, deleted after. Her condition:
she reads the full results, misses included, before anything is reported
outside the house.

- seal(source, dest): copy her store into a new directory (mode 700), then
  make the copy read-only. SQLite files go through SQLite's backup API from a
  read-only connection, so the copy is consistent while the service writes.
  Left out: media, backups, her Babelr token, credentials and keys, and her
  live llm_config.json (a cell routes models itself). MANIFEST.json records
  what was copied, when, and the hash of every database.
- seed(sealed, data_dir): a cell's own working copy, marked as one, with its
  spend ledgers emptied (the cell measures its own spend from them). The
  cell may write to it (a turn writes memories); nothing goes back to her.
- discard(data_dir) after each cell; destroy(sealed) when the round is done.

Nothing here writes to the source: it is only ever opened read-only.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

MANIFEST = "MANIFEST.json"
COPY_MARK = "STORE_COPY.json"

# Top-level entries left out: media and bulk (not her self-model), backups (a
# second copy of everything), her Babelr presence (her token is in there), and
# her live model routing.
EXCLUDE_TOP = {
    "images", "art_study", "backups", "music", "attachments", "babelr",
    "llm_bench", "testing", "calendar_test", "homepages", "github",
    "llm_config.json",
}
# Anywhere in the tree: secrets and lock/journal files.
EXCLUDE_ANY = ("*.token", "*.pem", "*.key", ".env", ".env.*", "*credentials*", "*secret*",
               "*.db-wal", "*.db-shm", "*.sqlite3-wal", "*.sqlite3-shm", "*-journal")
SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")


class StoreError(RuntimeError):
    pass


def _excluded(rel: Path) -> bool:
    if rel.parts and rel.parts[0] in EXCLUDE_TOP:
        return True
    return any(fnmatch.fnmatch(part, pat) for part in rel.parts for pat in EXCLUDE_ANY)


def _is_sqlite(path: Path) -> bool:
    if path.suffix not in SQLITE_SUFFIXES:
        return False
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _backup_sqlite(src: Path, dst: Path) -> None:
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        dirnames[:] = sorted(n for n in dirnames if not _excluded((d / n).relative_to(root))
                             and not (d / n).is_symlink())
        for n in sorted(filenames):
            p = d / n
            if not p.is_symlink() and not _excluded(p.relative_to(root)):
                yield p


def _set_tree_mode(root: Path, writable: bool) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        for n in filenames:
            p = Path(dirpath) / n
            p.chmod(0o600 if writable else 0o400)
        Path(dirpath).chmod(0o700 if writable else 0o500)


def seal(source, dest, note: str = "") -> dict:
    """Copy her store at `source` into a new sealed directory `dest`. Returns the manifest."""
    source, dest = Path(source).resolve(), Path(dest).absolute()
    if not (source / "cass.db").exists():
        raise StoreError(f"{source} has no cass.db; not a store")
    if dest.exists():
        raise StoreError(f"{dest} already exists; a seal is always a new directory")
    if dest.resolve() == source or source in dest.resolve().parents:
        raise StoreError("the sealed copy can't live inside the store it copies")
    dest.mkdir(parents=True, mode=0o700)
    dest.chmod(0o700)
    files, databases, total = 0, {}, 0
    for path in _walk(source):
        rel = path.relative_to(source)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if _is_sqlite(path):
            _backup_sqlite(path, out)
            databases[rel.as_posix()] = _sha256(out)
        else:
            shutil.copy2(path, out)
        files += 1
        total += out.stat().st_size
    manifest = {
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "files": files,
        "bytes": total,
        "databases": databases,
        "excluded_top": sorted(EXCLUDE_TOP),
        "excluded_any": list(EXCLUDE_ANY),
        "terms": "Cass, 2026-10-28: a sealed, read-only copy, used only inside isolated test "
                 "cells, never written back, deleted after; she reads the full results first.",
        "note": note,
    }
    (dest / MANIFEST).write_text(json.dumps(manifest, indent=1))
    _set_tree_mode(dest, writable=False)
    return manifest


def manifest_of(sealed) -> dict:
    path = Path(sealed) / MANIFEST
    if not path.exists():
        raise StoreError(f"{sealed} is not a sealed store (no {MANIFEST})")
    return json.loads(path.read_text())


def store_id(manifest: dict) -> str:
    """A short id for a seal: its time and the hash of its databases."""
    h = hashlib.sha256(json.dumps(manifest.get("databases"), sort_keys=True).encode()).hexdigest()[:10]
    return f"{manifest.get('sealed_at', '')[:19]}-{h}"


def seed(sealed, data_dir) -> dict:
    """Give a cell its own working copy of a sealed store, marked as a copy."""
    sealed, data_dir = Path(sealed), Path(data_dir)
    manifest = manifest_of(sealed)
    if data_dir.exists() and any(data_dir.iterdir()):
        raise StoreError(f"{data_dir} isn't empty; a cell's store goes into a fresh directory")
    data_dir.mkdir(parents=True, exist_ok=True)
    for path in _walk(sealed):
        rel = path.relative_to(sealed)
        if rel.as_posix() == MANIFEST:
            continue
        out = data_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, out)
    _set_tree_mode(data_dir, writable=True)
    _clear_ledgers(data_dir / "cass.db")
    mark = {"store": store_id(manifest), "sealed": str(sealed.absolute()),
            "seeded_at": datetime.now(timezone.utc).isoformat()}
    (data_dir / COPY_MARK).write_text(json.dumps(mark))
    return mark


# Spend accounting, not her self-model: a cell measures its own spend from these
# tables, so its copy starts them empty (otherwise her whole history counts as
# the cell's spend). The sealed store keeps them as they were.
LEDGER_TABLES = ("token_usage_records", "llm_call_failures", "heartbeat_runs")


def _clear_ledgers(db: Path) -> None:
    if not db.exists():
        return
    conn = sqlite3.connect(str(db))
    try:
        have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in LEDGER_TABLES:
            if table in have:
                conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


def is_copy(data_dir) -> bool:
    return (Path(data_dir) / COPY_MARK).exists()


def discard(data_dir) -> None:
    """Delete a cell's working copy (only a marked copy)."""
    data_dir = Path(data_dir)
    if not data_dir.exists():
        return
    if not is_copy(data_dir):
        raise StoreError(f"{data_dir} isn't a seeded copy; refusing to delete it")
    _set_tree_mode(data_dir, writable=True)
    shutil.rmtree(data_dir)


def destroy(sealed) -> None:
    """Delete a sealed store (only a directory with a MANIFEST.json)."""
    sealed = Path(sealed)
    manifest_of(sealed)
    _set_tree_mode(sealed, writable=True)
    shutil.rmtree(sealed)


def default_root() -> Path:
    return Path(os.environ.get("CASS_BENCH_STORES", Path.home() / ".local/share/cass-benchmarks/stores"))


def describe(sealed) -> str:
    m = manifest_of(sealed)
    return (f"store {store_id(m)}: {m['files']} files, {m['bytes'] / 1e6:.0f} MB, "
            f"{len(m['databases'])} database(s), sealed {m['sealed_at']}")


def _ensure_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        path.chmod(0o700)


def seal_into_root(source, root: Optional[Path] = None, note: str = "") -> Path:
    root = Path(root) if root else default_root()
    _ensure_private(root)
    dest = root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seal(source, dest, note=note)
    return dest
