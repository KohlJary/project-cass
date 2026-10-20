#!/usr/bin/env python3
"""
Daily backup of Cass's data directory, run by the cass-backup user timer
(scripts/systemd/). Writes cass-YYYY-MM-DD-HHMM.zip to CASS_BACKUP_DIR (or
--out), then prunes to the last 7 days and 4 weeks.

The data directory is config.DATA_DIR: $DATA_DIR, from the environment or
backend/.env, else backend/data. Needs no running server and no login.

    python scripts/backup.py --out ~/cass/backups
"""
import argparse
import os
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
    out_dir.mkdir(parents=True, exist_ok=True)

    path = daily_backup_path(out_dir, datetime.now())
    write_backup(DATA_DIR, path)
    print(f"Backed up {DATA_DIR} -> {path} ({path.stat().st_size / 1e9:.2f} GB)")
    for old in prune(out_dir, args.keep_daily, args.keep_weekly):
        print(f"Pruned {old.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
