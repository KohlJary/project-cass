"""
Mint a read-only token for her room feed (routes/room.py). Run by Kohl; the
token is printed once and only its hash is kept (DATA_DIR/room/tokens.json).

    python scripts/room_token.py kohl "Babelr room plugin"      # sees all she shared
    python scripts/room_token.py house "Babelr room, house"     # only what she shared with the house

Place it where the room plugin reads it; it is sent as "Authorization: Bearer <token>".
Revoke by deleting its entry from tokens.json.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mint a room feed token")
    ap.add_argument("audience", choices=["kohl", "house"])
    ap.add_argument("name", help="what it's for, e.g. 'Babelr room plugin'")
    ap.add_argument("--data-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    from room import mint_token
    token = mint_token(a.audience, a.name, a.data_dir)
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
