"""Two bugs her agenda flagged in a test session (2026-11-13)."""
import asyncio


def test_recall_journal_opens_the_daily_journal_not_a_research_one():
    from handlers.journals import execute_journal_tool

    class Memory:
        def get_daily_journal_entry(self, date):
            return {"content": "Kohl and I talked late into the night.", "metadata": {"timestamp": "t"}}

        def get_journal_entry(self, date):
            return {"content": "Research summary: Egyptian tomb architecture.", "metadata": {"timestamp": "t"}}

    out = asyncio.run(execute_journal_tool("recall_journal", {"date": "2026-11-12"}, memory=Memory()))
    assert "Kohl and I talked" in out["result"] and "Research summary" not in out["result"]


def test_recall_journal_falls_back_when_there_is_no_daily_one():
    from handlers.journals import execute_journal_tool

    class Memory:
        def get_daily_journal_entry(self, date):
            return None

        def get_journal_entry(self, date):
            return {"content": "Research summary.", "metadata": {}}

    out = asyncio.run(execute_journal_tool("recall_journal", {"date": "2026-11-12"}, memory=Memory()))
    assert "Research summary." in out["result"]


def test_user_resolves_by_display_name_or_peopledex_name(daemon_id):
    from database import get_db
    from handlers.user_model import resolve_user_id
    from peopledex import PeopleDexManager
    with get_db() as conn:
        conn.execute("INSERT INTO users (id, display_name, created_at, updated_at) VALUES ('u-k', 'Kohl', 'now', 'now')")
    pdx = PeopleDexManager(daemon_id=daemon_id)
    entity = pdx.ensure_entity_for_user("u-k")
    pdx.update_entity(entity.id, primary_name="KohlJary")
    assert resolve_user_id("Kohl") == "u-k"          # vessel display name
    assert resolve_user_id("kohljary") == "u-k"      # PeopleDex name
    assert resolve_user_id("u-k") == "u-k"           # already an id
    assert resolve_user_id("Nobody") is None
