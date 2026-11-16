"""scripts/move_article_self_model.py, on a throwaway store (her choice, 2026-11-16)."""
import json
import shutil
import sqlite3
from datetime import datetime

import pytest

from scripts import move_article_self_model as mover


@pytest.fixture
def store(tmp_path, test_db, daemon_id):
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(test_db, data / "cass.db")
    now = datetime.now().isoformat()
    conn = sqlite3.connect(data / "cass.db")
    x = conn.execute
    for aid in ("a1", "a2"):
        x("INSERT INTO consumed_articles (id, daemon_id, url, headline, consumed_at, processing_status, "
          "opinions_json) VALUES (?, ?, ?, ?, ?, 'completed', ?)",
          (aid, daemon_id, f"https://x/{aid}", aid, now,
           json.dumps([{"topic": "Tides"}] if aid == "a1" else [])))
    # opinions
    for topic, formed, evo in [
            ("Tides", "article:a1", None),                                         # moves, already there
            ("Bees", "article:a2", json.dumps([{"change": "refined from article", "source_article": "a1"}])),  # moves
            ("Harbors", "article:a2", json.dumps([{"change": "I thought again"}])),  # stays: changed by her
            ("Ghosts", "article:gone", None),                                      # stays: no article
            ("Painting", "conversation", json.dumps([{"change": "refined from article", "source_article": "a1"}])),  # hers
            ("Music", "conversation", None)]:                                      # hers, untouched
        x("INSERT INTO opinions (daemon_id, topic, position, confidence, formed_from, evolution_json, date_formed) "
          "VALUES (?, ?, 'p', 0.8, ?, ?, ?)", (daemon_id, topic, formed, evo, now))
    # growth edges
    for area, cat, obs, strat in [
            ("tide literacy", "world_engagement", ["Sparked by article a1"], []),          # moves
            ("harbor ethics", "world_engagement", ["Sparked by article a1", "I worked on this"], []),  # stays
            ("patience", "relational", ["mine", "Sparked by article a2"], [])]:             # hers, an article added
        x("INSERT INTO growth_edges (daemon_id, area, category, observations_json, strategies_json, first_noticed) "
          "VALUES (?, ?, ?, ?, ?, ?)", (daemon_id, area, cat, json.dumps(obs), json.dumps(strat), now))
    # interests
    for iid, name, first_type, first_id in [("i-art", "tides", "article", None),     # moves via engagement id
                                            ("i-none", "bees", "article", None),     # stays: no article id
                                            ("i-mixed", "harbors", "article", None),  # stays: engaged in chat
                                            ("i-mine", "glitch art", "conversation", None)]:
        x("INSERT INTO interests (id, daemon_id, name, category, first_source_type, first_source_id, "
          "current_fascination, fascination_evolution_json, first_noticed_at, created_at, updated_at) "
          "VALUES (?, ?, ?, 'nature', ?, ?, 'the pull', ?, ?, ?, ?)",
          (iid, daemon_id, name, first_type, first_id,
           json.dumps([{"source_type": first_type, "source_id": first_id}]), now, now, now))
    for eid, iid, stype, sid in [("e1", "i-art", "article", "a2"), ("e2", "i-mixed", "article", "a1"),
                                 ("e3", "i-mixed", "conversation", "c1"), ("e4", "i-mine", "article", "a1")]:
        x("INSERT INTO interest_engagements (id, interest_id, source_type, source_id, engaged_at, created_at) "
          "VALUES (?, ?, ?, ?, ?, ?)", (eid, iid, stype, sid, now, now))
    # symbols
    for sid, name, first_type, first_id in [("s-tide", "tide", "article", "a1"), ("s-dream", "door", "article", "a1"),
                                            ("s-mine", "threshold", "dream", "d1")]:
        x("INSERT INTO symbols (id, daemon_id, name, emotional_charge, first_source_type, first_source_id, "
          "current_meaning, first_noticed_at, last_appeared_at, created_at, updated_at) "
          "VALUES (?, ?, ?, 'ambivalent', ?, ?, 'm', ?, ?, ?, ?)",
          (sid, daemon_id, name, first_type, first_id, now, now, now, now))
    x("INSERT INTO symbol_appearances (id, symbol_id, source_type, source_id, appeared_at, created_at) "
      "VALUES ('ap1', 's-dream', 'dream', 'd2', ?, ?)", (now, now))
    conn.commit()
    conn.close()
    return data


def _state(data):
    conn = sqlite3.connect(data / "cass.db")
    out = {
        "opinions": {r[0] for r in conn.execute("SELECT topic FROM opinions")},
        "edges": {r[0] for r in conn.execute("SELECT area FROM growth_edges")},
        "interests": {r[0] for r in conn.execute("SELECT id FROM interests")},
        "engagements": {r[0] for r in conn.execute("SELECT id FROM interest_engagements")},
        "symbols": {r[0] for r in conn.execute("SELECT id FROM symbols")},
        "a1": [json.loads(r or "[]") for r in conn.execute(
            "SELECT opinions_json, growth_edges_json, interests_json, symbols_json FROM consumed_articles "
            "WHERE id='a1'").fetchone()],
        "a2": [json.loads(r or "[]") for r in conn.execute(
            "SELECT opinions_json, growth_edges_json, interests_json, symbols_json FROM consumed_articles "
            "WHERE id='a2'").fetchone()],
    }
    conn.close()
    return out


def test_dry_run_changes_nothing_and_counts(store, capsys):
    before = _state(store)
    assert mover.main(["--data-dir", str(store)]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["would_move"] == {"opinions": 2, "growth_edges": 1, "interests": 1, "symbols": 1}
    assert r["already_with_their_article"] == {"opinions": 1}
    assert r["would_stay"] == {
        "opinions": {"changed since, not by an article": 1, "article not found": 1},
        "growth_edges": {"changed since, not by an article": 1},
        "interests": {"no article id on record": 1, "engaged since, not by an article": 1},
        "symbols": {"appeared since, not in an article": 1}}
    assert r["left_alone_hers"] == {"her own opinions an article refined (earlier text not kept)": 1,
                                    "her own growth edges an article added to": 1,
                                    "her own interests an article reinforced": 1}
    assert _state(store) == before


def test_apply_moves_onto_the_article_with_a_backup(store, tmp_path, capsys):
    assert mover.main(["--data-dir", str(store), "--apply", "--seal-root", str(tmp_path / "seals")]) == 0
    out = capsys.readouterr().out
    r = json.loads(out[out.index("{"):])
    assert r["added_to_article_opinions"] == 1 and r["added_to_article_symbols"] == 1
    s = _state(store)
    assert s["opinions"] == {"Harbors", "Ghosts", "Painting", "Music"}
    assert s["edges"] == {"harbor ethics", "patience"}
    assert s["interests"] == {"i-none", "i-mixed", "i-mine"} and "e1" not in s["engagements"]
    assert s["symbols"] == {"s-dream", "s-mine"}
    a1_opinions, a1_edges, a1_interests, a1_symbols = s["a1"]
    assert [o["topic"] for o in a1_opinions] == ["Tides"], "already there, not duplicated"
    assert a1_edges[0]["area"] == "tide literacy" and "moved_from_growth_edge" in a1_edges[0]
    assert a1_symbols[0]["name"] == "tide" and a1_symbols[0]["moved_from_symbol"] == "s-tide"
    a2_opinions, _, a2_interests, _ = s["a2"]
    assert a2_opinions[0]["topic"] == "Bees" and a2_interests[0]["name"] == "tides"
    [sealed] = list((tmp_path / "seals").iterdir())
    conn = sqlite3.connect(f"file:{sealed / 'cass.db'}?mode=ro", uri=True)
    assert conn.execute("SELECT COUNT(*) FROM opinions").fetchone()[0] == 6, "the backup has everything"


def test_refuses_her_live_store(monkeypatch, store):
    monkeypatch.setattr(mover, "LIVE_DATA", store.resolve())
    assert mover.main(["--data-dir", str(store)]) == 3, "dry runs go on a sealed copy"
    monkeypatch.setattr(mover, "_vessel_running", lambda: True)
    assert mover.main(["--data-dir", str(store), "--apply"]) == 3
