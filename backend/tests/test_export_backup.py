"""
Exports and backups reach the real data (#16, #17, #18).

- /export/* reads config.DATA_DIR, not repo-root/data.
- /export/backup zips every database and Chroma, and the zip restores.
- A .anima export carries PeopleDex, threads, questions, symbols, interests,
  and the journals and marks that live only in Chroma, and they round-trip.
"""
import sqlite3
import uuid
from datetime import datetime
from zipfile import ZipFile

import chromadb
import pytest
from chromadb.config import Settings
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from tests.conftest import _point_db_at

NOW = datetime(2026, 10, 20, 12, 0, 0).isoformat()


def _client(chroma_path):
    return chromadb.PersistentClient(path=str(chroma_path), settings=Settings(anonymized_telemetry=False))


@pytest.fixture
def export_app():
    from routes.export import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# --- #16 ---------------------------------------------------------------------

def test_export_routes_read_config_data_dir():
    import routes.export as export
    assert export.DATA_DIR == config.DATA_DIR


def test_wiki_export_returns_page_written_under_data_dir(export_app, tmp_path, monkeypatch):
    import wiki
    from wiki.storage import WikiStorage

    storage = WikiStorage(wiki_root=str(tmp_path / "wiki"), git_enabled=False)
    monkeypatch.setattr(wiki, "_storage_instance", storage)
    storage.create("lasagna", "# Lasagna\n\nForty years of the same recipe.", commit=False)

    body = export_app.get("/export/wiki/json").json()
    assert "lasagna" in [p["name"] for p in body["pages"]]


# --- #17 ---------------------------------------------------------------------

@pytest.fixture
def seeded_data_dir(tmp_path, monkeypatch):
    import routes.export as export

    data = tmp_path / "data"
    data.mkdir()

    db = sqlite3.connect(data / "cass.db")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, body TEXT)")
    db.execute("INSERT INTO notes VALUES ('n1', 'runny yolks')")
    db.commit()
    # Left open: the committed row sits in the WAL, which the backup must fold in.

    _client(data / "chroma").get_or_create_collection("cass_memory").add(
        ids=["m1"], documents=["the elephant is Greg's favorite"], embeddings=[[0.1, 0.2, 0.3]],
    )

    (data / "wiki").mkdir()
    (data / "wiki" / "page.md").write_text("hello")
    (data / "backups").mkdir()
    (data / "backups" / "backup_old.zip").write_bytes(b"not me")

    monkeypatch.setattr(export, "DATA_DIR", data)
    yield data
    db.close()


def test_backup_contains_databases_and_chroma_and_restores(export_app, seeded_data_dir, tmp_path):
    resp = export_app.post("/export/backup")
    assert resp.status_code == 200
    backup = resp.json()["backup_path"]

    with ZipFile(backup) as zf:
        names = set(zf.namelist())
        assert "cass.db" in names
        assert "chroma/chroma.sqlite3" in names
        assert "wiki/page.md" in names
        assert not any(n.startswith("backups/") for n in names)
        assert not any(n.endswith(("-wal", "-shm")) for n in names)
        restored = tmp_path / "restored"
        zf.extractall(restored)

    db = sqlite3.connect(restored / "cass.db")
    assert db.execute("SELECT body FROM notes WHERE id='n1'").fetchone() == ("runny yolks",)
    db.close()

    got = _client(restored / "chroma").get_collection("cass_memory").get(ids=["m1"])
    assert got["documents"] == ["the elephant is Greg's favorite"]

    listed = export_app.get("/export/backups").json()["backups"]
    assert [b["filename"] for b in listed if b["filename"] != "backup_old.zip"] == [backup.rsplit("/", 1)[1]]


# --- #18 ---------------------------------------------------------------------

def _seed_daemon(daemon_id):
    from database import get_db
    ids = {k: str(uuid.uuid4()) for k in ("conv", "thread", "question", "entity", "attr", "obs", "fact")}
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (id, daemon_id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (ids["conv"], daemon_id, "user-1", "eggs", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO conversation_threads (id, daemon_id, user_id, title, first_conversation_id, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (ids["thread"], daemon_id, "user-1", "breakfast preferences", ids["conv"], NOW),
        )
        conn.execute(
            "INSERT INTO open_questions (id, daemon_id, user_id, question, source_conversation_id, source_thread_id, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (ids["question"], daemon_id, "user-1", "Whites set, yolks runny?", ids["conv"], ids["thread"], NOW),
        )
        conn.execute(
            "INSERT INTO symbols (id, daemon_id, name, first_noticed_at, last_appeared_at, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), daemon_id, "wings", NOW, NOW, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO interests (id, daemon_id, name, first_noticed_at, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), daemon_id, "lasagna", NOW, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO peopledex_entities (id, entity_type, primary_name, created_at, updated_at) VALUES (?,?,?,?,?)",
            (ids["entity"], "person", "Greg", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO peopledex_attributes (id, entity_id, attribute_type, value, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (ids["attr"], ids["entity"], "note", "likes elephants", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO peopledex_observations (id, entity_id, daemon_id, observation_type, content, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (ids["obs"], ids["entity"], daemon_id, "value", "says love you on the way out", NOW),
        )
        conn.execute(
            "INSERT INTO peopledex_facts (id, entity_id, daemon_id, fact_type, content, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (ids["fact"], ids["entity"], None, "preference", "whites set, yolks runny", NOW, NOW),
        )
    return ids


def test_anima_round_trips_peopledex_threads_questions_and_chroma_records(
    daemon_id, seeded_users, fake_embeddings, tmp_path, monkeypatch,
):
    from database import get_db
    from database.migrations import init_database
    from markers import Mark, MarkerStore
    from memory import core as memory_core
    from memory import CassMemory
    import daemon_export

    ids = _seed_daemon(daemon_id)

    # Source instance's Chroma: one nightly journal, one mark on the conversation
    src_chroma = tmp_path / "src_chroma"
    monkeypatch.setattr(memory_core, "CHROMA_PERSIST_DIR", str(src_chroma))
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "src_data")
    memory = CassMemory()
    memory._core.collection.add(
        ids=["journal-1"],
        documents=["Greg made it to work. I bought eggs."],
        metadatas=[{"type": "journal", "journal_date": "2026-10-19", "is_journal": True, "timestamp": NOW}],
    )
    MarkerStore(client=memory._core.client).store_mark(Mark(
        id="mark-1", category="care", description="the eggs", context_window="whites set",
        conversation_id=ids["conv"], timestamp=NOW, position=0,
    ))

    anima = tmp_path / "cass.anima"
    result = daemon_export.export_daemon(daemon_id, anima, include_users=True)
    assert result["stats"]["chroma_journals"] == 1
    assert result["stats"]["chroma_marks"] == 1

    # Fresh instance: empty schema, empty Chroma, empty DATA_DIR
    _point_db_at(tmp_path / "fresh.db")
    init_database()
    monkeypatch.setattr(memory_core, "CHROMA_PERSIST_DIR", str(tmp_path / "dst_chroma"))
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "dst_data")

    out = daemon_export.import_daemon(anima, skip_embeddings=True)
    assert out["chroma_counts"] == {"journals": 1, "marks": 1}

    with get_db() as conn:
        def one(sql, *args):
            return conn.execute(sql, args).fetchone()

        # Shared PeopleDex rows keep their ids; daemon-scoped ones still point at them
        assert one("SELECT primary_name FROM peopledex_entities WHERE id=?", ids["entity"])[0] == "Greg"
        assert one("SELECT value FROM peopledex_attributes WHERE entity_id=?", ids["entity"])[0] == "likes elephants"
        assert one("SELECT content FROM peopledex_facts WHERE entity_id=?", ids["entity"])[0] == "whites set, yolks runny"
        assert one("SELECT content FROM peopledex_observations WHERE entity_id=?", ids["entity"])[0] == \
            "says love you on the way out"

        conv_id = one("SELECT id FROM conversations WHERE title='eggs'")[0]
        thread_id, first_conv = one(
            "SELECT id, first_conversation_id FROM conversation_threads WHERE title='breakfast preferences'")
        assert first_conv == conv_id
        q_conv, q_thread = one(
            "SELECT source_conversation_id, source_thread_id FROM open_questions WHERE question LIKE 'Whites%'")
        assert (q_conv, q_thread) == (conv_id, thread_id)
        assert one("SELECT name FROM symbols")[0] == "wings"
        assert one("SELECT name FROM interests")[0] == "lasagna"

    restored = CassMemory()
    journal = restored.get_journal_entry("2026-10-19")
    assert journal and "I bought eggs" in journal["content"]

    marks = MarkerStore(client=restored._core.client).collection.get(ids=["mark-1"])
    assert marks["metadatas"][0]["conversation_id"] == conv_id
