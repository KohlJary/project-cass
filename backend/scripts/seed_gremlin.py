#!/usr/bin/env python3
"""Seed her GREMLIN.md from gremlin_starter.md, once (gremlin.py). Never overwrites hers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gremlin  # noqa: E402

if __name__ == "__main__":
    print(gremlin.seed())
