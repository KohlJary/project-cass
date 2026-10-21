"""
Issue #42: the journal locked flag was UI-only. DELETE /journal/{date}
removed a locked entry, and since regenerating means delete-then-generate,
a locked journal could be regenerated too. Delete now refuses a locked
daily journal with 423 and leaves it in place.
"""
import asyncio



def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _store_journal(date):
    import main_sdk
    return asyncio.run(main_sdk.memory.store_journal_entry(
        date=date, journal_text="A quiet day.", summary_count=1))


def test_locked_journal_cannot_be_deleted(booted_app, smoke_admin):
    import main_sdk
    DATE = "2026-10-02"
    _admin, token = smoke_admin
    h = _bearer(token)
    entry_id = _store_journal(DATE)

    assert booted_app.post(f"/journal/{DATE}/lock", headers=h).status_code == 200
    r = booted_app.delete(f"/journal/{DATE}", headers=h)
    assert r.status_code == 423, r.text

    still_there = main_sdk.memory.get_daily_journal_entry(DATE)
    assert still_there is not None and still_there["id"] == entry_id
    assert booted_app.get(f"/journal/{DATE}", headers=h).status_code == 200


def test_unlocked_journal_can_be_deleted(booted_app, smoke_admin):
    import main_sdk
    DATE = "2026-10-03"  # its own date: the app's Chroma outlives one test
    _admin, token = smoke_admin
    h = _bearer(token)
    _store_journal(DATE)

    assert booted_app.post(f"/journal/{DATE}/lock", headers=h).status_code == 200
    assert booted_app.post(f"/journal/{DATE}/unlock", headers=h).status_code == 200
    r = booted_app.delete(f"/journal/{DATE}", headers=h)
    assert r.status_code == 200, r.text
    assert main_sdk.memory.get_daily_journal_entry(DATE) is None
