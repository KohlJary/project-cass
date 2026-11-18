#!/usr/bin/env python3
"""Pause or resume what Cass sends on a platform (posts, replies, DMs, follows).

    python scripts/social_pause.py bluesky                 # pause, as Kohl, until resumed
    python scripts/social_pause.py bluesky --until 2026-11-20T09:00 --reason "..."
    python scripts/social_pause.py bluesky --resume
    python scripts/social_pause.py bluesky --status

Takes effect on her next send; no restart. A pause Kohl sets, she can't lift
(social_pause tells her it's his).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from social import limits  # noqa: E402
from social.config import PLATFORMS  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("platform", choices=PLATFORMS)
    ap.add_argument("--until")
    ap.add_argument("--reason", default="")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        print(json.dumps(limits.paused(a.platform), indent=2))
    elif a.resume:
        print("resumed" if limits.resume(a.platform) else "wasn't paused")
    else:
        print(json.dumps(limits.pause(a.platform, "Kohl", a.reason, a.until), indent=2))


if __name__ == "__main__":
    main()
