"""
scripts/move_article_observations.py (plan "Cass's memory", item 8eb07bb8),
on a throwaway store: dry run changes nothing; apply seals a backup, keeps
each observation with its article, removes the self-observation copy and
its recall-pool entry, and leaves alone what it can't place.
"""
import json
import shutil
import sqlite3
from datetime import datetime

import pytest

from scripts import move_article_observations as mover


def _client(path):
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


@pytest.fixture
def store(tmp_path, test_db, daemon_id):
    pytest.importorskip("chromadb")
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(test_db, data / "cass.db")
    now = datetime.now().isoformat()
    conn = sqlite3.connect(data / "cass.db")
    conn.execute("INSERT INTO consumed_articles (id, daemon_id, url, headline, consumed_at, processing_status, "
                 "observations_json) VALUES ('a1', ?, 'https://x/1', 'Harbor', ?, 'completed', ?)",
                 (daemon_id, now, json.dumps([{"text": "Tides are rising", "confidence": 0.8, "category": "trend"}])))
    rows = [
        ("o-in", "world_awareness:trend", "Tides are rising", {"source": "article", "article_id": "a1"}),
        ("o-new", "world_awareness:concern", "Harbor  funding is short", {"source": "article", "article_id": "a1"}),
        ("o-orphan", "world_awareness:trend", "Lost article", {"source": "article", "article_id": "gone"}),
        ("o-mine", "pattern", "I slow down at night", {}),
        ("o-world", "world_awareness", "Rain all week, said Kohl", {}),
    ]
    for oid, cat, text, ctx in rows:
        conn.execute("INSERT INTO self_observations (id, daemon_id, category, observation, confidence, "
                     "context_json, created_at) VALUES (?, ?, ?, ?, 0.7, ?, ?)",
                     (oid, daemon_id, cat, text, json.dumps(ctx), now))
    conn.commit()
    conn.close()
    col = _client(data / "chroma").get_or_create_collection("cass_memory")
    col.add(ids=[f"cass_self_observation_{r[0]}" for r in rows] + ["conv-1"],
            documents=[r[2] for r in rows] + ["User: hi\nCass: hi"],
            embeddings=[[0.1, 0.2, 0.3]] * (len(rows) + 1),
            metadatas=[{"type": "cass_self_observation", "category": r[1]} for r in rows] + [{"type": "conversation"}])
    return data


def _state(data):
    conn = sqlite3.connect(data / "cass.db")
    obs = {r[0] for r in conn.execute("SELECT id FROM self_observations")}
    kept = json.loads(conn.execute("SELECT observations_json FROM consumed_articles WHERE id='a1'").fetchone()[0])
    conn.close()
    pool = set(_client(data / "chroma").get_collection("cass_memory").get(include=[])["ids"])
    return obs, kept, pool


def test_dry_run_changes_nothing(store, capsys):
    before = _state(store)
    assert mover.main(["--data-dir", str(store)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["would_move"] == 2 and report["already_with_their_article"] == 1
    assert report["would_add_to_their_article_first"] == 1 and report["would_stay"] == 1
    assert _state(store) == before


def test_apply_moves_to_the_article_with_a_backup(store, tmp_path, capsys):
    assert mover.main(["--data-dir", str(store), "--apply", "--seal-root", str(tmp_path / "seals")]) == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{"):])
    assert report["moved"] == 2 and report["added_to_article"] == 1
    assert report["removed_from_recall_pool"] == 2 and report["stayed"] == 1
    obs, kept, pool = _state(store)
    # Hers and her own world notes stay; the orphan stays; the moved ones are gone.
    assert obs == {"o-orphan", "o-mine", "o-world"}
    texts = [k["text"] for k in kept]
    assert texts.count("Tides are rising") == 1 and "Harbor  funding is short" in texts
    assert next(k for k in kept if k.get("moved_from_self_observation") == "o-new")["category"] == "concern"
    assert "cass_self_observation_o-in" not in pool and "cass_self_observation_o-mine" in pool
    assert "conv-1" in pool
    # The backup is a sealed copy that still has everything.
    [sealed] = list((tmp_path / "seals").iterdir())
    conn = sqlite3.connect(f"file:{sealed / 'cass.db'}?mode=ro", uri=True)
    assert conn.execute("SELECT COUNT(*) FROM self_observations").fetchone()[0] == 5


def test_apply_refuses_the_live_store_while_the_vessel_runs(monkeypatch, store):
    monkeypatch.setattr(mover, "LIVE_DATA", store.resolve())
    monkeypatch.setattr(mover, "_vessel_running", lambda: True)
    assert mover.main(["--data-dir", str(store), "--apply"]) == 3
