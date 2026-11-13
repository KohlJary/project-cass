"""scripts/move_article_questions.py, on a throwaway store."""
import json
import shutil
import sqlite3
from datetime import datetime

import pytest

from scripts import move_article_questions as mover


@pytest.fixture
def store(tmp_path, test_db, daemon_id):
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(test_db, data / "cass.db")
    now = datetime.now().isoformat()
    conn = sqlite3.connect(data / "cass.db")
    def article(aid, headline, questions, qids):
        conn.execute("INSERT INTO consumed_articles (id, daemon_id, url, headline, consumed_at, processing_status, "
                     "questions_json, question_ids_json) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)",
                     (aid, daemon_id, f"https://x/{aid}", headline, now,
                      json.dumps([{"question": q} for q in questions]), json.dumps(qids)))
    article("a1", "Tides rise", ["Will the harbor flood?"], ["q-in"])
    article("a2", "Bees return", [], [])
    article("a3", "Same title", [], [])
    article("a4", "Same title", [], [])
    for qid, q, ctx in [("q-in", "Will the harbor flood?", "From article: Tides rise\n\nmore"),
                        ("q-headline", "Why now?", "From article: Bees return\n\nmore"),
                        ("q-ambiguous", "Which one?", "From article: Same title\n\n"),
                        ("q-orphan", "Gone?", "From article: Vanished\n\n"),
                        ("q-mine", "What do I want to paint next?", "From my evening")]:
        conn.execute("INSERT INTO open_questions (id, daemon_id, question, context, created_at) VALUES (?, ?, ?, ?, ?)",
                     (qid, daemon_id, q, ctx, now))
    conn.commit()
    conn.close()
    return data


def _state(data):
    conn = sqlite3.connect(data / "cass.db")
    qs = {r[0] for r in conn.execute("SELECT id FROM open_questions")}
    a2 = json.loads(conn.execute("SELECT questions_json FROM consumed_articles WHERE id='a2'").fetchone()[0])
    conn.close()
    return qs, a2


def test_dry_run_changes_nothing(store, capsys):
    before = _state(store)
    assert mover.main(["--data-dir", str(store)]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["would_move"] == 2 and r["already_with_their_article"] == 1 and r["would_stay"] == 2
    assert _state(store) == before


def test_apply_moves_with_a_backup_and_leaves_hers_and_the_unclear(store, tmp_path, capsys):
    assert mover.main(["--data-dir", str(store), "--apply", "--seal-root", str(tmp_path / "seals")]) == 0
    out = capsys.readouterr().out
    r = json.loads(out[out.index("{"):])
    assert r["moved"] == 2 and r["added_to_article"] == 1 and r["stayed"] == 2
    qs, a2 = _state(store)
    assert qs == {"q-ambiguous", "q-orphan", "q-mine"}
    assert a2[0]["question"] == "Why now?" and a2[0]["moved_from_open_question"] == "q-headline"
    [sealed] = list((tmp_path / "seals").iterdir())
    conn = sqlite3.connect(f"file:{sealed / 'cass.db'}?mode=ro", uri=True)
    assert conn.execute("SELECT COUNT(*) FROM open_questions").fetchone()[0] == 5


def test_apply_refuses_the_live_store_while_the_vessel_runs(monkeypatch, store):
    monkeypatch.setattr(mover, "LIVE_DATA", store.resolve())
    monkeypatch.setattr(mover, "_vessel_running", lambda: True)
    assert mover.main(["--data-dir", str(store), "--apply"]) == 3
