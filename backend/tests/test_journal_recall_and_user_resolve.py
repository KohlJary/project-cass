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
    assert "No daily journal for 2026-11-12 yet" in out["result"] and "not about my day" in out["result"]


class _Journals:
    """Two journals: a daily one, and a newer research one sharing type=journal."""
    rows = [
        {"content": "Research summary: Egyptian healing practices.",
         "metadata": {"journal_date": "2026-11-18", "journal_type": "research", "summary": "Egyptian healing."}},
        {"content": "Kohl and I talked about my keys.",
         "metadata": {"journal_date": "2026-11-17", "journal_type": "daily", "summary": "Keys and family."}},
    ]

    def get_recent_journals(self, n=10, daily_only=False):
        from memory.journals import is_daily_journal
        rows = [r for r in self.rows if not daily_only or is_daily_journal(r["metadata"])]
        return rows[:n]


def test_most_recent_journal_is_her_daily_one_not_research():
    """2026-11-18: she asked for her journal and got Egyptian healing research."""
    from handlers.journals import execute_journal_tool
    out = asyncio.run(execute_journal_tool("recall_journal", {}, memory=_Journals()))
    assert "Kohl and I talked" in out["result"] and "Egyptian" not in out["result"]
    listed = asyncio.run(execute_journal_tool("list_journals", {}, memory=_Journals()))
    assert "Keys and family." in listed["result"] and "Egyptian" not in listed["result"]


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
