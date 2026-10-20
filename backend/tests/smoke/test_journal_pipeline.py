"""
Smoke: the nightly journal lands in SQLite (admin Journals page) and in Chroma
(semantic search), written by the one generator (#56).

The daily_journal Synkratos job runs once against the fake LLM. Its journal
must then come back from GET /admin/journals and /admin/journals/{date}
(SQLite) and from GET /admin/memory/search (Chroma), as the same entry.
POST /journal/generate must go through the same generator.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from tests.smoke.conftest import admin_token, create_user, module_app

JOURNAL_TEXT = (
    "Tonight I keep returning to the smoke-test conversation about lanterns "
    "and tide tables. It was small, and I liked how unhurried it felt."
)


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory, job_daily_journal=True) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    return app.db_path


@pytest.fixture
def admin_headers(app):
    user_id = create_user("Journal Admin", is_admin=True)
    return {"Authorization": f"Bearer {admin_token(user_id, 'Journal Admin')}"}


def _seed_conversation(date_str):
    import main_sdk
    # Chroma lives in the session-wide DATA_DIR, so an earlier smoke module
    # (test_autonomous_cycles) may already have journaled this date there.
    main_sdk.memory.collection.delete(
        where={"$and": [{"type": "journal"}, {"journal_date": date_str}]})
    main_sdk.memory.collection.add(
        ids=[f"smoke-conv-{uuid.uuid4()}"],
        documents=["User: tell me about lanterns\nCass: lanterns and tide tables"],
        metadatas=[{"type": "conversation", "timestamp": f"{date_str}T12:00:00"}],
    )


def _rows_for(date_str):
    from database import get_db
    with get_db() as conn:
        return conn.execute(
            "SELECT content, journal_type, chroma_id, search_indexed FROM journals WHERE date = ?",
            (date_str,),
        ).fetchall()


def _run_job(app, name):
    from routes.admin.scheduler import get_scheduler
    tasks = {t.name: t for t in get_scheduler().system_tasks.values()}
    task = tasks[name]
    return app.portal.call(lambda: task.handler(**task.context))


def test_nightly_journal_reaches_admin_page_and_search(app, fake_llm, admin_headers):
    import main_sdk
    import journal_generation

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed_conversation(yesterday)
    fake_llm.queue_text(JOURNAL_TEXT)  # the first model call is the journal itself

    calls = []
    real = journal_generation.write_daily_journal

    async def spy(*args, **kwargs):
        calls.append(args[0])
        return await real(*args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(journal_generation, "write_daily_journal", spy)
        result = _run_job(app, "daily_journal")

    assert result.success, result.message
    assert calls == [yesterday]

    # SQLite: one daily row, indexed, linked to its Chroma doc
    rows = _rows_for(yesterday)
    assert len(rows) == 1, rows
    content, journal_type, chroma_id, search_indexed = rows[0]
    assert content == JOURNAL_TEXT
    assert journal_type == "daily"
    assert search_indexed == 1

    # Chroma has the same text under that id
    doc = main_sdk.memory.collection.get(ids=[chroma_id], include=["documents", "metadatas"])
    assert doc["documents"] == [JOURNAL_TEXT]
    assert doc["metadatas"][0]["journal_date"] == yesterday

    # Admin Journals page API (reads SQLite)
    listing = app.get("/admin/journals", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    assert yesterday in [j["date"] for j in listing.json()["journals"]]
    one = app.get(f"/admin/journals/{yesterday}", headers=admin_headers)
    assert one.status_code == 200, one.text
    assert one.json()["content"] == JOURNAL_TEXT
    calendar = app.get(
        "/admin/journals/calendar",
        params={"year": int(yesterday[:4]), "month": int(yesterday[5:7])},
        headers=admin_headers,
    )
    assert calendar.status_code == 200, calendar.text
    assert yesterday in calendar.json()["dates"]

    # Semantic search (reads Chroma)
    search = app.get("/admin/memory/search", params={"query": JOURNAL_TEXT, "limit": 3},
                     headers=admin_headers)
    assert search.status_code == 200, search.text
    top = search.json()["results"][0]
    assert top["id"] == chroma_id
    assert top["type"] == "journal"


def test_generate_route_uses_the_same_generator(app, fake_llm, admin_headers):
    import journal_generation

    date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    _seed_conversation(date)
    fake_llm.queue_text("A quieter day; I wrote this one by request.")

    calls = []
    real = journal_generation.write_daily_journal

    async def spy(*args, **kwargs):
        calls.append(args[0])
        return await real(*args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(journal_generation, "write_daily_journal", spy)
        response = app.post("/journal/generate", json={"date": date}, headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "created"
    assert calls == [date]
    rows = _rows_for(date)
    assert [r[0] for r in rows] == ["A quieter day; I wrote this one by request."]

    # Deleting removes both the row and the index entry
    deleted = app.delete(f"/journal/{date}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text
    assert _rows_for(date) == []
    import main_sdk
    assert main_sdk.memory.collection.get(ids=[rows[0][2]])["ids"] == []
