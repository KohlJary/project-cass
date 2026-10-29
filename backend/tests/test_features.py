"""Feature levers (features.py): precedence, profiles, legacy env vars, wiring."""
import asyncio
import logging

import pytest

import features


@pytest.fixture
def clean_env(monkeypatch):
    """No profile and no lever env vars, so defaults show through."""
    monkeypatch.delenv("CASS_PROFILE", raising=False)
    for lever in features.LEVERS.values():
        monkeypatch.delenv(lever.env_var, raising=False)
        for alias in lever.aliases:
            monkeypatch.delenv(alias, raising=False)
    return monkeypatch


class TestResolution:
    def test_defaults_match_current_production_behavior(self, clean_env):
        # Production must be unchanged when nothing is set.
        assert features.resolve("scheduler") == (True, "default")
        assert features.resolve("thymos") == (True, "default")
        assert features.resolve("autonomous_scheduling") == (True, "default")
        assert features.resolve("discord") == (False, "default")
        assert features.resolve("relay") == (False, "default")

    def test_legacy_env_var_still_works(self, clean_env):
        clean_env.setenv("AUTONOMOUS_SCHEDULING_ENABLED", "false")
        assert features.resolve("autonomous_scheduling") == (False, "env:AUTONOMOUS_SCHEDULING_ENABLED")
        clean_env.setenv("DISCORD_ENABLED", "true")
        assert features.resolve("discord") == (True, "env:DISCORD_ENABLED")

    def test_feature_env_var_overrides_default(self, clean_env):
        clean_env.setenv("CASS_FEATURE_THYMOS", "0")
        assert features.resolve("thymos") == (False, "env:CASS_FEATURE_THYMOS")

    def test_test_profile_turns_everything_off(self, clean_env):
        """Everything that starts on its own; prompt switches are left as they are."""
        clean_env.setenv("CASS_PROFILE", "test")
        assert not any(features.is_enabled(name) for name, lv in features.LEVERS.items()
                       if features.PROMPT not in lv.tags)
        assert all(features.resolve(name) == (True, "default") for name, lv in features.LEVERS.items()
                   if features.PROMPT in lv.tags)

    def test_quiet_profile_only_turns_off_llm_and_integrations(self, clean_env):
        clean_env.setenv("CASS_PROFILE", "quiet")
        assert features.resolve("job_daily_journal") == (False, "profile:quiet")   # llm
        assert features.resolve("home_assistant") == (False, "profile:quiet")      # integration
        assert features.resolve("thymos") == (True, "default")                    # neither
        assert features.resolve("scheduler") == (True, "default")

    def test_explicit_lever_env_beats_profile(self, clean_env):
        clean_env.setenv("CASS_PROFILE", "test")
        clean_env.setenv("CASS_FEATURE_THYMOS", "1")
        assert features.resolve("thymos") == (True, "env:CASS_FEATURE_THYMOS")

    def test_profile_beats_legacy_env_var(self, clean_env):
        clean_env.setenv("CASS_PROFILE", "test")
        clean_env.setenv("AUTONOMOUS_SCHEDULING_ENABLED", "true")
        assert features.resolve("autonomous_scheduling") == (False, "profile:test")

    def test_override_beats_everything_and_is_undone(self, clean_env, levers):
        clean_env.setenv("CASS_FEATURE_THYMOS", "0")
        with levers(thymos=True):
            assert features.resolve("thymos") == (True, "override")
        assert features.resolve("thymos") == (False, "env:CASS_FEATURE_THYMOS")

    def test_unknown_lever_is_an_error(self, levers):
        with pytest.raises(KeyError):
            features.is_enabled("thymoss")
        with pytest.raises(KeyError):
            with levers(thymoss=True):
                pass

    def test_garbage_env_value_is_ignored(self, clean_env):
        clean_env.setenv("CASS_FEATURE_THYMOS", "maybe")
        assert features.resolve("thymos") == (True, "default")

    def test_conftest_default_profile_is_test(self):
        assert features.active_profile() == "test"

    def test_action_prefix_mapping(self):
        assert features.lever_for_action("rss.check_feeds") == "rss"
        assert features.lever_for_action("artstudy.get_status") == "art_study"
        assert features.lever_for_action("goals.get_next") is None


class TestStartupLogAndEndpoint:
    def test_lever_table_logged(self, caplog):
        with caplog.at_level(logging.INFO, logger="features"):
            features.log_lever_table()
        assert "CASS_PROFILE=test" in caplog.text
        assert "scheduler" in caplog.text


class TestWiring:
    """Each lever actually gates its subsystem's start point."""

    def test_system_jobs_respect_their_levers(self, levers):
        from scheduler import Synkratos, BudgetManager, BudgetConfig
        from scheduler.system_tasks import register_system_tasks

        managers = {
            "github_metrics_manager": object(),
            "conversation_manager": object(),
            "memory": object(),
            "generate_missing_journals": lambda **k: None,
        }

        def registered(**on):
            synkratos = Synkratos(BudgetManager(BudgetConfig()))
            with levers(**on):
                register_system_tasks(synkratos, managers, enabled=True)
            return {t.name for t in synkratos.system_tasks.values()}

        assert registered() == set()
        assert registered(job_github_metrics=True, job_goal_refinement=True) == {
            "github_metrics", "goal_refinement"}
        all_on = registered(job_github_metrics=True, job_idle_summarization=True,
                            job_daily_journal=True, job_goal_refinement=True)
        assert all_on == {"github_metrics", "idle_summarization", "daily_journal", "goal_refinement"}

    async def test_action_domain_lever_blocks_execution(self, levers):
        from scheduler.actions import ActionRegistry

        calls = []

        async def handler(context):
            calls.append(context)
            return {"success": True}

        registry = ActionRegistry()
        registry.load_definitions()
        registry.register_handler("rss.get_status", handler)

        result = await registry.execute("rss.get_status")
        assert not result.success and "lever 'rss'" in result.message
        assert calls == []

        with levers(rss=True):
            result = await registry.execute("rss.get_status")
        assert result.success and len(calls) == 1

    async def test_grimoire_tick_hook_respects_levers(self, levers):
        from grimoire.manager import create_grimoire_hooks

        class StubManager:
            def __init__(self):
                self.calls = []

            async def check_and_execute_timer_triggers(self):
                self.calls.append("timer")
                return []

            async def check_and_execute_need_triggers(self, needs):
                self.calls.append("need")
                return []

            async def check_and_execute_affect_triggers(self, affects):
                self.calls.append("affect")
                return []

        manager = StubManager()
        on_tick, _ = create_grimoire_hooks(manager)

        await on_tick({}, {})
        assert manager.calls == []

        with levers(grimoire_timer_spells=True):
            await on_tick({}, {})
        assert manager.calls == ["timer"]

        manager.calls.clear()
        with levers(grimoire_need_spells=True):
            await on_tick({}, {})
        assert manager.calls == ["need", "affect"]

    async def test_push_respects_lever(self, levers):
        from relay_client import RelayClient

        client = RelayClient.__new__(RelayClient)
        sent = []

        async def fake_send(msg):
            sent.append(msg)
            return True

        client.send = fake_send
        assert await client.send_push("u", "t", "b") is False
        assert sent == []
        with levers(push=True):
            assert await client.send_push("u", "t", "b") is True
        assert len(sent) == 1

    def test_face_and_voice_id_respect_levers(self, levers):
        import face_identification
        import voice_identification

        assert face_identification.is_available() is False
        with pytest.raises(RuntimeError, match="lever 'voice_id'"):
            voice_identification.get_encoder()

    async def test_geocass_respects_lever(self):
        from geocass_sync import sync_to_connection, GeoCassConnection

        conn = GeoCassConnection.__new__(GeoCassConnection)
        conn.id = "c1"
        result = await sync_to_connection(conn, "cass", "Cass", "d1")
        assert result.success is False and "lever 'geocass'" in result.error
