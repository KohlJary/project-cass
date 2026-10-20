"""
Backups of the data directory (config.DATA_DIR): one zip with every database,
Chroma, and the file stores. Restore by unzipping into an empty DATA_DIR.

Used by POST /export/backup and by scripts/backup.py (the daily timer). Stdlib
only, so the script runs without starting any of the backend.
"""
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

BACKUP_DIR_NAME = "backups"

# SQLite sidecar files: the backup API copies their committed contents into
# the main file, so the sidecars themselves are never zipped.
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
_SQLITE_HEADER = b"SQLite format 3\x00"

# Already compressed; deflating them again only costs time.
_STORED_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".ogg", ".flac",
    ".m4a", ".mp4", ".webm", ".zip", ".gz", ".anima",
}


def _is_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
    except OSError:
        return False


def _data_files(data_dir: Path, skip: Path):
    """Every file under data_dir except under skip, following symlinked
    directories (once each, so a link cycle can't loop)."""
    seen = set()
    for root, dirs, files in os.walk(data_dir, followlinks=True):
        real = os.path.realpath(root)
        if real in seen or Path(root).is_relative_to(skip):
            dirs[:] = []
            continue
        seen.add(real)
        dirs.sort()
        for name in sorted(files):
            path = Path(root) / name
            if path.is_file():
                yield path


def _snapshot_sqlite(src_path: Path, dst_path: Path) -> None:
    """Consistent copy of a live SQLite database.

    Copied a few hundred pages per step, so a writer on a rollback-journal
    database (cass.db) waits at most one step, not the whole copy. If another
    connection writes mid-copy, SQLite restarts the copy, so the result is
    always one committed state.
    """
    src = sqlite3.connect(src_path.resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst, pages=256, sleep=0.01)
    finally:
        dst.close()
        src.close()


def write_backup(data_dir: Path, backup_path: Path) -> None:
    """Zip everything under data_dir except the backups themselves.

    SQLite databases (cass.db, Chroma's chroma.sqlite3, the rest; found by
    header) go through the SQLite backup API, so each lands as one committed
    state with its WAL folded in, and their sidecar files are left out.

    Plain files are copied first and databases last. Chroma keeps its vectors
    in segment files and its documents and write log in chroma.sqlite3, so
    copying the segments first means the log is never older than the vectors.
    A Chroma write landing during the backup can still leave a vector out of
    the segments; the document itself is in the sqlite snapshot.

    The zip is written under a temporary name and renamed when complete, so
    /export/backups never lists a half-written backup, and a failed backup
    leaves nothing behind.
    """
    partial = backup_path.with_name(backup_path.name + ".partial")
    files, databases = [], []
    for file in _data_files(data_dir, data_dir / BACKUP_DIR_NAME):
        if file.name.endswith(_SQLITE_SIDECARS):
            continue
        (databases if _is_sqlite(file) else files).append(file)
    try:
        with tempfile.TemporaryDirectory() as snap_dir, ZipFile(partial, "w") as zf:
            for file in files:
                compress = ZIP_STORED if file.suffix.lower() in _STORED_SUFFIXES else ZIP_DEFLATED
                zf.write(file, str(file.relative_to(data_dir)), compress_type=compress)
            for file in databases:
                snapshot = Path(snap_dir) / "snapshot.db"
                _snapshot_sqlite(file, snapshot)
                zf.write(snapshot, str(file.relative_to(data_dir)), compress_type=ZIP_DEFLATED)
                snapshot.unlink()
        partial.rename(backup_path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


# Daily backups written by scripts/backup.py: cass-YYYY-MM-DD-HHMM.zip
DAILY_NAME = re.compile(r"^cass-(\d{4}-\d{2}-\d{2})-(\d{4})\.zip$")


def daily_backup_path(out_dir: Path, now: datetime) -> Path:
    return out_dir / f"cass-{now:%Y-%m-%d-%H%M}.zip"


def prune(out_dir: Path, keep_daily: int = 7, keep_weekly: int = 4) -> List[Path]:
    """Delete daily backups beyond retention and return what was deleted.

    Keeps the newest backup of each of the last keep_daily days that have one,
    and the newest backup of each of the keep_weekly ISO weeks before those.
    Only files named like daily backups are considered; anything else in
    out_dir (manual snapshots, other tools' files) is never touched.
    """
    backups = sorted(
        (p for p in out_dir.iterdir() if DAILY_NAME.match(p.name)),
        key=lambda p: p.name, reverse=True,
    )
    keep, days, weeks = set(), [], []
    for p in backups:
        day = DAILY_NAME.match(p.name).group(1)
        if day in days:
            continue
        if len(days) < keep_daily:
            days.append(day)
            keep.add(p)
            continue
        week = datetime.strptime(day, "%Y-%m-%d").isocalendar()[:2]
        if week not in weeks and len(weeks) < keep_weekly:
            weeks.append(week)
            keep.add(p)
        days.append(day)
    deleted = [p for p in backups if p not in keep]
    for p in deleted:
        p.unlink()
    return deleted
