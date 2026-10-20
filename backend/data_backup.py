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


def _data_files(data_dir: Path, skip: Iterable[Path]):
    """Every file under data_dir except under the skip directories, following
    symlinked directories (once each, so a link cycle can't loop). A skip
    directory is matched by its real path too, so a symlink inside data_dir
    that leads to it is skipped as well."""
    skip_real = [Path(os.path.realpath(p)) for p in skip]
    seen = set()
    for root, dirs, files in os.walk(data_dir, followlinks=True):
        real = os.path.realpath(root)
        if real in seen or any(Path(real).is_relative_to(s) for s in skip_real):
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
    # Never back up a backup: skip the route's backups/ folder, and the
    # folder this one is written to, even through a symlink in data_dir
    # (unless that folder contains data_dir, when skipping it would skip
    # everything), and the zip being written itself.
    out_real = Path(os.path.realpath(backup_path.parent))
    skip = [data_dir / BACKUP_DIR_NAME]
    if not Path(os.path.realpath(data_dir)).is_relative_to(out_real):
        skip.append(out_real)
    writing = {os.path.realpath(partial), os.path.realpath(backup_path)}
    for file in _data_files(data_dir, skip):
        if file.name.endswith(_SQLITE_SIDECARS) or os.path.realpath(file) in writing:
            continue
        (databases if _is_sqlite(file) else files).append(file)
    try:
        # Snapshots go next to the zip, not to /tmp, which may be RAM.
        with tempfile.TemporaryDirectory(dir=backup_path.parent, prefix=".snap-") as snap_dir, \
                ZipFile(partial, "w") as zf:
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


def _backup_day(path: Path):
    """The date in a daily backup's name, or None if it isn't one (wrong name,
    impossible date, not a regular file)."""
    match = DAILY_NAME.match(path.name)
    if not match or not path.is_file():
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def prune(out_dir: Path, keep_daily: int = 7, keep_weekly: int = 4) -> List[Path]:
    """Delete daily backups beyond retention and return what was deleted.

    Keeps the newest backup of each of the keep_daily most recent days that
    have a backup (days, not calendar days: if the timer stops, the last good
    ones are kept, not aged out), then the newest backup of each of the
    keep_weekly ISO weeks older than those days. Only regular files named
    like daily backups, with a real date, are considered; anything else in
    out_dir (manual snapshots, other tools' files) is never touched.
    """
    if keep_daily < 1 or keep_weekly < 0:
        raise ValueError("keep at least one daily backup, and a non-negative number of weekly ones")
    dated = [(p, d) for p in out_dir.iterdir() if (d := _backup_day(p)) is not None]
    dated.sort(key=lambda pd: pd[0].name, reverse=True)
    keep, seen_days, daily_days, daily_weeks, weekly_weeks = set(), set(), set(), set(), set()
    for p, day in dated:
        if day in seen_days:
            continue  # an older backup from a day already handled
        seen_days.add(day)
        week = day.isocalendar()[:2]
        if len(daily_days) < keep_daily:
            keep.add(p)
            daily_days.add(day)
            daily_weeks.add(week)  # a week with a daily keeper needs no weekly one
        elif week not in daily_weeks and week not in weekly_weeks and len(weekly_weeks) < keep_weekly:
            keep.add(p)
            weekly_weeks.add(week)
    backups = [p for p, _ in dated]
    deleted = [p for p in backups if p not in keep]
    for p in deleted:
        p.unlink()
    return deleted
