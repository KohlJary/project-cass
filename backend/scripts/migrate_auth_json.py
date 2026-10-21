#!/usr/bin/env python3
"""Copy the old per-user auth.json credentials into the SQLite users table (#61).

There used to be two credential stores: SQLite users (display name +
password_hash, used by the admin dashboard) and DATA_DIR/users/<id>/auth.json
(email + password_hash, used by the mobile app's /auth/login). This copies
each auth.json into its users row:

  - users.email empty           -> set to the auth.json email
  - users.email differs         -> auth.json email goes in users.legacy_email
  - users.password_hash empty   -> set to the auth.json hash
  - users.password_hash differs -> auth.json hash goes in users.legacy_password_hash

Login (auth.authenticate) accepts the row's values and the legacy ones, so
every email/password pair that worked before keeps working.

Never deletes or edits auth.json files, never deletes rows, never overwrites a
non-empty users column. Idempotent: a second run changes nothing. Prints user
ids and counts only, never emails or hashes.

Dry run by default (opens the database read-only):
    DATA_DIR=/path/to/copy python scripts/migrate_auth_json.py
    DATA_DIR=/path/to/copy python scripts/migrate_auth_json.py --apply
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

LEGACY_COLUMNS = ("legacy_email", "legacy_password_hash")


def _columns(conn) -> set:
    return {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}


def _counts(conn, columns: set) -> dict:
    def n(where):
        return conn.execute(f"SELECT COUNT(*) FROM users WHERE {where}").fetchone()[0]
    out = {
        "users": n("1=1"),
        "with_password_hash": n("password_hash IS NOT NULL AND password_hash != ''"),
        "with_email": n("email IS NOT NULL AND email != ''"),
    }
    for col in LEGACY_COLUMNS:
        out[f"with_{col}"] = n(f"{col} IS NOT NULL AND {col} != ''") if col in columns else 0
    return out


def _email_owner(conn, email: str, columns: set):
    sql = "SELECT id FROM users WHERE LOWER(email) = LOWER(?)"
    params = [email]
    if "legacy_email" in columns:
        sql += " OR LOWER(legacy_email) = LOWER(?)"
        params.append(email)
    return [r[0] for r in conn.execute(sql, params).fetchall()]


def plan(conn, users_dir: Path, columns: set):
    """Return (actions, tally). actions: list of (user_id, {column: value})."""
    tally = Counter()
    actions = []
    files = sorted(users_dir.glob("*/auth.json")) if users_dir.is_dir() else []
    tally["auth_json_files"] = len(files)
    for path in files:
        user_id = path.parent.name
        try:
            data = json.loads(path.read_text())
            email = (data.get("email") or "").strip().lower()
            pw_hash = (data.get("password_hash") or "").strip()
        except Exception:
            tally["unreadable"] += 1
            print(f"  {user_id}: auth.json unreadable, skipped")
            continue

        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            tally["no_users_row"] += 1
            print(f"  {user_id}: no users row, skipped (auth.json left in place)")
            continue
        row = dict(row)
        updates = {}

        if email:
            current = (row.get("email") or "").strip().lower()
            legacy = (row.get("legacy_email") or "").strip().lower()
            others = [o for o in _email_owner(conn, email, columns) if o != user_id]
            if current == email or legacy == email:
                tally["email_already_present"] += 1
            elif others:
                tally["email_used_by_other_user"] += 1
                print(f"  {user_id}: auth.json email belongs to another user row, not copied")
            elif not current:
                updates["email"] = email
                tally["email_set"] += 1
            else:
                updates["legacy_email"] = email
                tally["email_conflict_to_legacy"] += 1
        else:
            tally["no_email"] += 1

        if pw_hash:
            current = (row.get("password_hash") or "").strip()
            legacy = (row.get("legacy_password_hash") or "").strip()
            if current == pw_hash or legacy == pw_hash:
                tally["hash_already_present"] += 1
            elif not current:
                updates["password_hash"] = pw_hash
                tally["hash_set"] += 1
            else:
                updates["legacy_password_hash"] = pw_hash
                tally["hash_conflict_to_legacy"] += 1
        else:
            tally["no_hash"] += 1

        if updates:
            actions.append((user_id, updates))
            print(f"  {user_id}: will set {', '.join(sorted(updates))}")
        else:
            tally["unchanged"] += 1
    return actions, tally


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR"),
                        help="directory holding cass.db and users/ (default: $DATA_DIR)")
    parser.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    args = parser.parse_args(argv)
    if not args.data_dir:
        parser.error("set --data-dir or DATA_DIR")

    data_dir = Path(args.data_dir).resolve()
    db_path = data_dir / "cass.db"
    if not db_path.exists():
        print(f"No database at {db_path}")
        return 1

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] {db_path}")
    if args.apply:
        conn = sqlite3.connect(db_path, timeout=30)
    else:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        columns = _columns(conn)
        missing = [c for c in LEGACY_COLUMNS if c not in columns]
        before = _counts(conn, columns)
        print(f"Before: {before}")

        if missing:
            if args.apply:
                for col in missing:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                columns = _columns(conn)
                print(f"Added columns: {', '.join(missing)}")
            else:
                print(f"Would add columns: {', '.join(missing)} (schema v62)")
                # Plan as if they existed (empty).
        actions, tally = plan(conn, data_dir / "users", columns)

        print(f"Tally: {dict(sorted(tally.items()))}")
        print(f"Rows to update: {len(actions)}")

        if args.apply and actions:
            now = datetime.now().isoformat()
            for user_id, updates in actions:
                # Only fill empty columns: the WHERE re-checks so a concurrent
                # change is never overwritten.
                for col, value in updates.items():
                    conn.execute(
                        f"UPDATE users SET {col} = ?, updated_at = ? "
                        f"WHERE id = ? AND ({col} IS NULL OR {col} = '')",
                        (value, now, user_id),
                    )
            conn.commit()

        after = _counts(conn, _columns(conn))
        print(f"After:  {after}" + ("" if args.apply else " (dry run: unchanged)"))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
