#!/usr/bin/env python3
"""
Daily backup of Cass's data directory, run by the cass-backup user timer
(backend/cass-backup.service.template and cass-backup.timer). Writes cass-YYYY-MM-DD-HHMM.zip to CASS_BACKUP_DIR (or
--out), then prunes to the last 7 days and 4 weeks.

The data directory is config.DATA_DIR: $DATA_DIR, from the environment or
backend/.env, else backend/data. Needs no running server and no login.

    python scripts/backup.py --out ~/cass/backups
"""
import argparse
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR  # noqa: E402
from data_backup import daily_backup_path, prune, write_backup  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--out", default=os.getenv("CASS_BACKUP_DIR"),
                        help="where backups go (default: $CASS_BACKUP_DIR)")
    parser.add_argument("--keep-daily", type=int, default=7)
    parser.add_argument("--keep-weekly", type=int, default=4)
    args = parser.parse_args(argv)
    if not args.out:
        parser.error("set --out or CASS_BACKUP_DIR")

    out_dir = Path(args.out).expanduser().resolve()
    if out_dir.is_relative_to(DATA_DIR):
        parser.error(f"{out_dir} is inside the data directory it backs up")
    # config creates DATA_DIR if it's missing, so an unmounted or renamed
    # data dir would otherwise back up as an empty folder and, a week later,
    # be all that's left. Her main database must be there.
    main_db = DATA_DIR / "cass.db"
    if not main_db.is_file() or main_db.stat().st_size == 0:
        print(f"Refusing to back up {DATA_DIR}: {main_db.name} is missing or empty", file=sys.stderr)
        return 1
    if args.keep_daily < 1 or args.keep_weekly < 0:
        parser.error("--keep-daily must be at least 1 and --keep-weekly at least 0")
    out_dir.mkdir(parents=True, exist_ok=True)

    # A run cut short by a signal or a crash leaves a .partial nothing else
    # would remove; the timer runs one backup at a time, so sweep them first.
    for stale in out_dir.glob("cass-*.zip.partial"):
        stale.unlink()
    for stale in out_dir.glob(".snap-*"):
        if stale.is_dir():
            for f in stale.iterdir():
                f.unlink()
            stale.rmdir()

    # systemd stops units with SIGTERM; turn it into an exception so the
    # partial zip is removed on the way out.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    path = daily_backup_path(out_dir, datetime.now())
    write_backup(DATA_DIR, path)
    print(f"Backed up {DATA_DIR} -> {path} ({path.stat().st_size / 1e9:.2f} GB)")
    for old in prune(out_dir, args.keep_daily, args.keep_weekly):
        print(f"Pruned {old.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
