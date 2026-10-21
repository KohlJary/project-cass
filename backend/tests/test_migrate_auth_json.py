"""scripts/migrate_auth_json.py (#61): auth.json credentials into SQLite users.

Runs on a throwaway data dir with a minimal users table (pre-v62, so the
legacy_* columns are missing, as on a live database before migration).
"""
import json
import sqlite3
from contextlib import contextmanager

import pytest

from scripts import migrate_auth_json


def _make_data_dir(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    conn = sqlite3.connect(data / "cass.db")
    conn.execute(
        "CREATE TABLE users (id TEXT PRIMARY KEY, display_name TEXT NOT NULL, "
        "password_hash TEXT, is_admin INTEGER DEFAULT 0, status TEXT DEFAULT 'approved', "
        "rejection_reason TEXT, email TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    rows = [
        ("same", "Same", "$2b$hash-same", None),        # auth.json hash equals row
        ("differs", "Differs", "$2b$hash-row", "row@example.com"),
        ("empty", "Empty", None, None),
        ("other", "Other", None, "taken@example.com"),
    ]
    for uid, name, pw, email in rows:
        conn.execute("INSERT INTO users (id, display_name, password_hash, email, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, 'now', 'now')", (uid, name, pw, email))
    conn.commit()
    conn.close()

    def auth(uid, email, pw):
        d = data / "users" / uid
        d.mkdir(parents=True)
        (d / "auth.json").write_text(json.dumps({"email": email, "password_hash": pw,
                                                 "created_at": "then"}))
    auth("same", "same@example.com", "$2b$hash-same")
    auth("differs", "json@example.com", "$2b$hash-json")
    auth("empty", "Empty@Example.com", "$2b$hash-empty")
    auth("ghost", "ghost@example.com", "$2b$hash-ghost")      # no users row
    auth("conflict", "taken@example.com", "$2b$x")            # no row either
    (data / "users" / "broken").mkdir()
    (data / "users" / "broken" / "auth.json").write_text("{not json")
    return data


def _snapshot(data):
    conn = sqlite3.connect(data / "cass.db")
    conn.row_factory = sqlite3.Row
    rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM users")}
    conn.close()
    files = {p: p.read_bytes() for p in (data / "users").glob("*/auth.json")}
    return rows, files


def test_dry_run_changes_nothing(tmp_path):
    data = _make_data_dir(tmp_path)
    before = _snapshot(data)
    assert migrate_auth_json.main(["--data-dir", str(data)]) == 0
    assert _snapshot(data) == before


def test_apply_copies_without_overwriting_and_is_idempotent(tmp_path, capsys):
    data = _make_data_dir(tmp_path)
    _rows, files_before = _snapshot(data)

    assert migrate_auth_json.main(["--data-dir", str(data), "--apply"]) == 0
    rows, files_after = _snapshot(data)
    assert files_after == files_before          # auth.json never touched
    assert len(rows) == 4                       # no rows added or removed

    assert rows["same"]["email"] == "same@example.com"
    assert rows["same"]["legacy_password_hash"] is None
    # Disagreeing values go to legacy_*; the row's own values stay.
    assert rows["differs"]["email"] == "row@example.com"
    assert rows["differs"]["legacy_email"] == "json@example.com"
    assert rows["differs"]["password_hash"] == "$2b$hash-row"
    assert rows["differs"]["legacy_password_hash"] == "$2b$hash-json"
    # Empty columns are filled; email is lower-cased.
    assert rows["empty"]["email"] == "empty@example.com"
    assert rows["empty"]["password_hash"] == "$2b$hash-empty"
    assert rows["other"]["legacy_email"] is None

    out = capsys.readouterr().out
    assert "hash-" not in out and "@example.com" not in out  # ids and counts only

    assert migrate_auth_json.main(["--data-dir", str(data), "--apply"]) == 0
    assert _snapshot(data)[0] == rows
    assert "Rows to update: 0" in capsys.readouterr().out


def test_login_query_works_before_v62_columns_exist(tmp_path, monkeypatch):
    """A database without legacy_* columns must not lock anyone out."""
    pytest.importorskip("bcrypt")
    pytest.importorskip("jwt")
    import auth
    import database

    import secrets
    pw = secrets.token_urlsafe(12)
    data = _make_data_dir(tmp_path)
    conn = sqlite3.connect(data / "cass.db")
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE users SET password_hash = ? WHERE id = 'empty'",
                 (auth.hash_password(pw),))
    conn.execute("UPDATE users SET email = 'empty@example.com' WHERE id = 'empty'")
    conn.commit()

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(database, "get_db", fake_get_db)
    assert auth.authenticate("Empty", pw) == "empty"
    assert auth.authenticate("empty@example.com", pw) == "empty"
    assert auth.find_user_id_by_email("EMPTY@example.com") == "empty"
    conn.close()
