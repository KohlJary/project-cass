#!/usr/bin/env python3
"""Mint a token for the record (record.py), for Babelr's "Cass's record" plugin.

    python scripts/record_token.py "babelr record plugin"

Prints the token once; only its hash is kept (DATA_DIR/record/tokens.json).
Put it in ~/.config/cass-record/kohl.token (mode 600) for the plugin.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from record import mint_token  # noqa: E402

if __name__ == "__main__":
    print(mint_token(" ".join(sys.argv[1:]) or "record"))
