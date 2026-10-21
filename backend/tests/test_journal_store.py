"""
Journals: SQLite is the source of truth, Chroma the search index (#56).

Covers store_journal_entry writing both, a failed Chroma write leaving a row
marked for re-index, reindex_pending_journals, delete, and the backfill script
(idempotent, never touches Chroma docs).
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import get_db


@pytest.fixture
def chroma(tmp_path, fake_embeddings):
    import chromadb
    from chromadb.config import Settings
    path = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
    return SimpleNamespace(path=path, collection=client.get_or_create_collection("cass_memory"))


@pytest.fixture
def manager(chroma):
    from memory.journals import JournalManager
    counter = iter(range(1000))
    core = SimpleNamespace(
        collection=chroma.collection,
        _generate_id=lambda *a: f"journal-{next(counter)}",
    )
    return JournalManager(core=core)


def _rows():
    with get_db() as conn:
        return conn.execute(
            "SELECT date, content, journal_type, chroma_id, search_indexed FROM journals "
            "ORDER BY created_at"
        ).fetchall()


def _store(manager, date="2026-10-19", text="I wrote this tonight.", journal_type="daily"):
    return asyncio.run(manager.store_journal_entry(
        date=date, journal_text=text, summary_count=2, journal_type=journal_type))


def test_store_writes_sqlite_row_and_chroma_doc(manager, chroma):
    entry_id = _store(manager)

    rows = _rows()
    assert [tuple(r) for r in rows] == [("2026-10-19", "I wrote this tonight.", "daily", entry_id, 1)]
    doc = chroma.collection.get(ids=[entry_id], include=["documents", "metadatas"])
    assert doc["documents"] == ["I wrote this tonight."]
    assert doc["metadatas"][0]["journal_type"] == "daily"


def test_side_journals_get_their_type(manager):
    _store(manager, journal_type="spell", text="a spell reflection")
    assert _rows()[0]["journal_type"] == "spell"


def test_chroma_failure_keeps_row_marked_for_reindex(manager, chroma, monkeypatch):
    monkeypatch.setenv("CASS_STRICT", "0")
    manager._core.collection = Mock(add=Mock(side_effect=RuntimeError("chroma down")))

    entry_id = _store(manager)

    row = _rows()[0]
    assert row["chroma_id"] == entry_id and row["search_indexed"] == 0

    manager._core.collection = chroma.collection
    assert manager.reindex_pending_journals() == 1
    assert _rows()[0]["search_indexed"] == 1
    assert chroma.collection.get(ids=[entry_id], include=["documents"])["documents"] == ["I wrote this tonight."]
    assert manager.reindex_pending_journals() == 0


def test_chroma_failure_is_loud_in_strict_mode(manager):
    manager._core.collection = Mock(add=Mock(side_effect=RuntimeError("chroma down")))
    with pytest.raises(RuntimeError):
        _store(manager)
    assert _rows()[0]["search_indexed"] == 0  # the row was written first


def test_delete_removes_row_and_index_entry(manager, chroma):
    entry_id = _store(manager)
    assert manager.delete_journal_entry("2026-10-19") == entry_id
    assert _rows() == []
    assert chroma.collection.get(ids=[entry_id])["ids"] == []


def test_delete_refuses_a_locked_journal(manager, chroma):
    from memory.journals import JournalLockedError
    entry_id = _store(manager)
    assert manager.set_journal_locked("2026-10-19", True)
    with pytest.raises(JournalLockedError):
        manager.delete_journal_entry("2026-10-19")
    assert [r["chroma_id"] for r in _rows()] == [entry_id]
    assert chroma.collection.get(ids=[entry_id])["ids"] == [entry_id]

    assert manager.set_journal_locked("2026-10-19", False)
    assert manager.delete_journal_entry("2026-10-19") == entry_id


# ---------------------------------------------------------------------------
# Backfill script
# ---------------------------------------------------------------------------

def _chroma_journal(collection, doc_id, date, text, **meta):
    collection.add(ids=[doc_id], documents=[text], metadatas=[{
        "type": "journal", "journal_date": date, "timestamp": f"{date}T23:00:00",
        "summary_count": 0, "conversation_count": 0, **meta}])


def test_backfill_copies_missing_and_is_idempotent(chroma):
    from scripts import backfill_journals_sqlite as backfill
    from memory.journals import insert_journal_row

    c = chroma.collection
    _chroma_journal(c, "j-daily", "2026-01-02", "daily text", summary_count=3)
    _chroma_journal(c, "j-spell", "2026-01-02", "spell text", journal_type="spell")
    _chroma_journal(c, "j-old", "2026-01-03", "What surprised me was the old side journal")
    _chroma_journal(c, "j-res", "2026-01-03", "The research session surprised me today")
    _chroma_journal(c, "j-seed", "2025-12-04", "seed text", summary_count=1)
    c.add(ids=["not-journal"], documents=["a summary"], metadatas=[{"type": "summary"}])
    # A pre-v60 seed row with the same date and text as a Chroma journal
    insert_journal_row(date="2025-12-04", content="seed text", created_at="x",
                       journal_type="daily", chroma_id=None)
    before_chroma = c.get(include=["documents", "metadatas"])

    dry = backfill.run(apply=False, persist_dir=chroma.path, collection_name="cass_memory")
    assert dry["missing"] == 4 and dry["inserted"] == 0
    assert dry["present_by_date_and_content"] == 1
    assert len(_rows()) == 1

    first = backfill.run(apply=True, persist_dir=chroma.path, collection_name="cass_memory")
    assert first["inserted"] == 4
    assert first["missing_by_type"] == {"daily": 1, "spell": 1, "untyped": 1, "research": 1}
    assert first["sqlite_rows_after"] == 5

    second = backfill.run(apply=True, persist_dir=chroma.path, collection_name="cass_memory")
    assert second["inserted"] == 0 and second["missing"] == 0
    assert second["present_by_chroma_id"] == 4

    after_chroma = c.get(include=["documents", "metadatas"])
    assert after_chroma == before_chroma  # Chroma untouched

    types = {r["chroma_id"]: r["journal_type"] for r in _rows() if r["chroma_id"]}
    assert types == {"j-daily": "daily", "j-spell": "spell", "j-old": "untyped", "j-res": "research"}


def test_daily_paths_ignore_side_journals_on_the_same_date(manager, chroma):
    research_id = _store(manager, text="research reflection", journal_type="research")
    daily_id = _store(manager, text="the daily journal")

    assert manager.get_daily_journal_entry("2026-10-19")["id"] == daily_id
    assert manager.delete_journal_entry("2026-10-19") == daily_id

    # The research journal on the same date is untouched, and is not a daily
    assert chroma.collection.get(ids=[research_id])["ids"] == [research_id]
    assert [r["chroma_id"] for r in _rows()] == [research_id]
    assert manager.get_daily_journal_entry("2026-10-19") is None
    assert manager.delete_journal_entry("2026-10-19") is None
