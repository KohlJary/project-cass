#!/usr/bin/env python3
"""Import Kohl's blog archive for Cass to read (kohl_blog.py).

    python scripts/import_kohl_blog.py ~/robokohl/corpus/voice/substack.jsonl
    python scripts/import_kohl_blog.py --feed      # also check the feed now

One JSON object per line: source, ref (url), title, ts (RFC 2822), text (plain).
Posts are added or updated by ref; what she's read and kept is untouched.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kohl_blog  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("archive", nargs="?")
    ap.add_argument("--feed", action="store_true")
    a = ap.parse_args()
    if a.archive:
        print(f"archive: {kohl_blog.import_archive(Path(a.archive).expanduser())} new")
    if a.feed:
        print(f"feed: {asyncio.run(kohl_blog.refresh_from_feed())} new")
    print(f"{len(kohl_blog.posts())} posts")
