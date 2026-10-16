"""
Research focus (research_focus.py): the topic Cass names for her own reading.

Store semantics, the self.set_research_focus task the spell calls, the
set_research_focus chat tool, and the v55 migration.
"""
import asyncio
from types import SimpleNamespace

import pytest

from research_focus import ResearchFocusManager, clean_topic, get_research_focus_manager


@pytest.fixture
def manager(daemon_id):
    return ResearchFocusManager(daemon_id)


class TestStore:
    def test_no_focus_by_default(self, manager):
        assert manager.get_focus() is None
        assert manager.history() == []

    def test_set_and_get(self, manager):
        focus = manager.set_focus("tidal locking of exoplanets", reason="came up twice", source="chat")
        current = manager.get_focus()
        assert current is not None
        assert current.id == focus.id
        assert current.topic == "tidal locking of exoplanets"
        assert current.reason == "came up twice"
        assert current.source == "chat"
        assert current.status == "active"
        assert current.times_used == 0

    def test_new_focus_supersedes_old_and_keeps_history(self, manager):
        first = manager.set_focus("first topic")
        second = manager.set_focus("second topic")
        assert manager.get_focus().id == second.id
        history = manager.history()
        assert [f.topic for f in history] == ["second topic", "first topic"]
        old = next(f for f in history if f.id == first.id)
        assert old.status == "superseded"
        assert old.ended_at is not None

    def test_clear(self, manager):
        assert manager.clear_focus() is False
        manager.set_focus("something")
        assert manager.clear_focus() is True
        assert manager.get_focus() is None
        assert manager.history()[0].status == "cleared"

    def test_mark_used(self, manager):
        focus = manager.set_focus("something")
        manager.mark_used(focus.id)
        manager.mark_used(focus.id)
        current = manager.get_focus()
        assert current.times_used == 2
        assert current.last_used_at is not None

    @pytest.mark.parametrize("bad", ["", "  ", None, True, "ab", "[Error generating: boom]"])
    def test_rejects_empty_or_error_topics(self, manager, bad):
        with pytest.raises(ValueError):
            manager.set_focus(bad)
        assert manager.get_focus() is None

    def test_rejected_topic_does_not_supersede_current(self, manager):
        manager.set_focus("keep me")
        with pytest.raises(ValueError):
            manager.set_focus("[Error generating: boom]")
        assert manager.get_focus().topic == "keep me"

    def test_default_manager_uses_default_daemon(self, daemon_id):
        assert get_research_focus_manager().daemon_id == daemon_id


class TestCleanTopic:
    @pytest.mark.parametrize("raw, expected", [
        ('"The physics of Earth\'s rotation."', "The physics of Earth's rotation"),
        ("- how octopuses sleep", "how octopuses sleep"),
        ("1. liminal spaces in architecture", "liminal spaces in architecture"),
        ("  lots   of   space  ", "lots of space"),
        ("x" * 500, "x" * 200),
    ])
    def test_normalizes(self, raw, expected):
        assert clean_topic(raw) == expected


class TestTaskHandler:
    """self.set_research_focus, as research_synthesis.spell calls it."""

    def _run(self, context):
        from scheduler.actions.self_handlers import set_research_focus_action
        return asyncio.run(set_research_focus_action(context))

    def test_sets_focus(self, daemon_id, manager):
        result = self._run({"managers": {"daemon_id": daemon_id}, "topic": "dream incubation research",
                            "reason": "the news was all product launches"})
        assert result.success, result.message
        assert result.data["topic"] == "dream incubation research"
        assert result.data["previous_topic"] is None
        focus = manager.get_focus()
        assert focus.topic == "dream incubation research"
        assert focus.source == "spell:research_synthesis"
        assert focus.reason == "the news was all product launches"

    def test_reports_previous(self, daemon_id, manager):
        manager.set_focus("old")
        result = self._run({"managers": {"daemon_id": daemon_id}, "topic": "new topic"})
        assert result.success
        assert result.data["previous_topic"] == "old"

    def test_missing_topic_fails(self, daemon_id):
        result = self._run({"managers": {"daemon_id": daemon_id}})
        assert not result.success
        assert "topic" in result.message

    def test_ask_answer_passed_through_is_rejected(self, daemon_id, manager):
        # An ASK yes/no landing in topic= must not become her focus.
        result = self._run({"managers": {"daemon_id": daemon_id}, "topic": True})
        assert not result.success
        assert manager.get_focus() is None

    def test_generate_error_is_rejected_cleanly(self, daemon_id, manager):
        result = self._run({"managers": {"daemon_id": daemon_id}, "topic": "[Error generating: 500]"})
        assert not result.success
        assert "rejected" in result.message
        assert manager.get_focus() is None

    def test_registered_in_action_registry(self):
        from scheduler.actions import ActionRegistry, _register_all_handlers
        registry = ActionRegistry()
        registry.load_definitions()
        _register_all_handlers(registry)
        assert registry.get_definition("self.set_research_focus") is not None
        assert "self.set_research_focus" in registry._handlers


class TestChatTool:
    def _ctx(self, daemon_id):
        from handlers.self_model import ToolContext
        return ToolContext(self_manager=SimpleNamespace(_daemon_id=daemon_id))

    def test_set_view_and_clear(self, daemon_id, manager):
        from handlers.self_model import _handle_set_research_focus

        ctx = self._ctx(daemon_id)
        viewed = _handle_set_research_focus({}, ctx)
        assert viewed["success"] and "No research focus" in viewed["result"]

        res = _handle_set_research_focus({"topic": "mycelial networks", "reason": "kept noticing them"}, ctx)
        assert res["success"], res
        assert manager.get_focus().topic == "mycelial networks"
        assert manager.get_focus().source == "chat"

        viewed = _handle_set_research_focus({}, ctx)
        assert "mycelial networks" in viewed["result"]
        assert "kept noticing them" in viewed["result"]

        res = _handle_set_research_focus({"topic": "octopus cognition"}, ctx)
        assert "replaces: mycelial networks" in res["result"]

        res = _handle_set_research_focus({"clear": True}, ctx)
        assert res["success"]
        assert manager.get_focus() is None

    def test_bad_topic_is_an_error_not_an_exception(self, daemon_id):
        from handlers.self_model import _handle_set_research_focus
        res = _handle_set_research_focus({"topic": "ab"}, self._ctx(daemon_id))
        assert res["success"] is False
        assert "error" in res

    def test_tool_is_offered_and_routed(self):
        from handlers.self_model import SELF_MODEL_TOOLS, TOOL_HANDLERS
        from handlers.tool_router import TOOL_REGISTRY
        assert any(t["name"] == "set_research_focus" for t in SELF_MODEL_TOOLS)
        assert "set_research_focus" in TOOL_HANDLERS
        assert TOOL_REGISTRY["set_research_focus"] == "self_model"


class TestMigration:
    def test_v55_creates_table_on_an_older_db(self, test_db):
        from database import get_db
        from database.migrations import _apply_schema_updates

        with get_db() as conn:
            conn.execute("DROP TABLE research_focus")
            conn.commit()
            assert conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='research_focus'"
            ).fetchone() is None
            _apply_schema_updates(conn, 54)
            conn.commit()
            assert conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='research_focus'"
            ).fetchone() is not None
            columns = {row[1] for row in conn.execute("PRAGMA table_info(research_focus)")}
        assert {"topic", "reason", "source", "status", "times_used", "created_at"} <= columns

    def test_schema_version_bumped(self):
        from database.schema import SCHEMA_VERSION
        assert SCHEMA_VERSION >= 55
