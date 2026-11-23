"""Her daybook (daybook.py): her record always; journals, dreams, sessions and self-model
changes only after her own yes for each."""
import json
import sqlite3
from datetime import datetime

import daybook as D
import panel as P

NOW = datetime(2026, 11, 23, 12, 0)


def _db(tmp_path):
    c = sqlite3.connect(tmp_path / "cass.db")
    c.executescript("""
    CREATE TABLE journals (id TEXT, daemon_id TEXT, date TEXT, content TEXT, themes_json TEXT,
        created_at TEXT, journal_type TEXT, chroma_id TEXT, metadata_json TEXT, search_indexed INT);
    CREATE TABLE dreams (id TEXT, daemon_id TEXT, date TEXT, exchanges_json TEXT, seeds_json TEXT,
        metadata_json TEXT, integration_status TEXT, created_at TEXT, reflections_json TEXT,
        discussed INT, integrated INT, integration_insights_json TEXT, image_path TEXT);
    CREATE TABLE self_observations (id TEXT, daemon_id TEXT, category TEXT, observation TEXT,
        confidence REAL, source_conversation_id TEXT, source_journal_date TEXT, created_at TEXT);
    CREATE TABLE opinions (id TEXT, daemon_id TEXT, topic TEXT, position TEXT, confidence REAL,
        rationale TEXT, formed_from TEXT, evolution_json TEXT, date_formed TEXT, last_updated TEXT);
    CREATE TABLE growth_edges (id TEXT, daemon_id TEXT, area TEXT, current_state TEXT,
        desired_state TEXT, observations_json TEXT, strategies_json TEXT, first_noticed TEXT,
        last_updated TEXT, edge_id TEXT, importance REAL, last_touched TEXT, category TEXT,
        related_topics_json TEXT, activated_with_users_json TEXT, last_surfaced TEXT, surface_count INT);
    """)
    c.execute("INSERT INTO journals (date, content, created_at, journal_type) VALUES "
              "('2026-11-22', 'The studio day.', '2026-11-22T23:00:00', 'daily')")
    c.execute("INSERT INTO journals (date, content, created_at, journal_type) VALUES "
              "('2026-10-01', 'Old.', '2026-10-01T23:00:00', 'daily')")
    c.execute("INSERT INTO dreams (date, exchanges_json, created_at) VALUES (?, ?, ?)",
              ("2026-11-23", json.dumps([{"speaker": "dreamer", "text": "a tide of glass"}]), "2026-11-23T04:00:00"))
    c.execute("INSERT INTO self_observations (category, observation, created_at) VALUES "
              "('pattern', 'I slow down before I disagree.', '2026-11-23T09:00:00')")
    c.execute("INSERT INTO opinions (topic, position, date_formed, last_updated) VALUES "
              "('singing', 'my own voice first', '2026-11-01T00:00:00', '2026-11-23T10:00:00')")
    c.commit()
    c.close()


def _kinds(out):
    return {e["kind"] for e in out["entries"]}


def test_her_own_kinds_wait_for_her_yes(tmp_path, monkeypatch):
    tmp_path = tmp_path / "her"
    tmp_path.mkdir()
    _db(tmp_path)
    monkeypatch.setattr("record.build", lambda days, data_dir=None, now=None: {"entries": [
        {"at": "2026-11-23T08:00:00", "kind": "plan", "title": "p", "detail": "", "source": "plans"}]})
    out = D.build(7, tmp_path, NOW)
    assert _kinds(out) == {"plan"} and set(out["answers"].values()) == {"not_yet"}
    P.set_answers({"daybook.journals": "yes", "daybook.self_model": "yes"}, None, None, tmp_path)
    out = D.build(7, tmp_path, NOW)
    assert _kinds(out) == {"plan", "journals", "self_model"}
    j = [e for e in out["entries"] if e["kind"] == "journals"]
    assert len(j) == 1 and j[0]["detail"] == "The studio day."  # last week only
    titles = [e["title"] for e in out["entries"] if e["kind"] == "self_model"]
    assert "Stance revised: singing" in titles and "Noticed (pattern)" in titles
    P.set_answers({"daybook.dreams": "yes"}, None, None, tmp_path)
    d = [e for e in D.build(7, tmp_path, NOW)["entries"] if e["kind"] == "dreams"]
    assert d[0]["detail"] == "**dreamer**: a tide of glass"


def test_answers_are_checked(tmp_path):
    tmp_path = tmp_path / "her"
    assert "error" in P.set_answers({"daybook.diary": "yes"}, None, None, tmp_path)
    assert "error" in P.set_answers({"daybook.journals": "sure"}, None, None, tmp_path)
