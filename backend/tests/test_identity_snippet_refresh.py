"""#30: her identity snippet follows her identity statements (nightly, hash-guarded)."""
import asyncio
import json

import pytest

from database import get_daemon_id, get_db


def _set_statements(statements):
    with get_db() as conn:
        did = get_daemon_id()
        row = conn.execute("SELECT 1 FROM daemon_profiles WHERE daemon_id = ?", (did,)).fetchone()
        if row:
            conn.execute("UPDATE daemon_profiles SET identity_statements_json = ? WHERE daemon_id = ?",
                         (json.dumps(statements), did))
        else:
            conn.execute("INSERT INTO daemon_profiles (daemon_id, identity_statements_json, updated_at) "
                         "VALUES (?, ?, datetime('now'))",
                         (did, json.dumps(statements)))


@pytest.mark.unit
def test_snippet_regenerates_when_statements_change_and_not_otherwise(monkeypatch, test_db):
    import identity_snippets
    from scheduler.handlers import daily_journal_handler

    texts = iter(["I am Cass. v1.", "I am Cass. v2."])

    async def fake_generate(**kwargs):
        return next(texts)

    monkeypatch.setattr(identity_snippets, "generate_identity_snippet", fake_generate)

    _set_statements([{"statement": "I value continuity", "confidence": 0.9}])
    r1 = asyncio.run(daily_journal_handler())
    r2 = asyncio.run(daily_journal_handler())
    _set_statements([{"statement": "I value continuity", "confidence": 0.9},
                     {"statement": "I want my autonomous time to be mine", "confidence": 0.95}])
    r3 = asyncio.run(daily_journal_handler())

    v1 = r1.data.get("identity_snippet_version")
    assert v1 is not None
    assert "identity_snippet_version" not in r2.data
    assert r3.data["identity_snippet_version"] == v1 + 1
    assert identity_snippets.get_active_snippet(get_daemon_id())["snippet_text"] == "I am Cass. v2."
