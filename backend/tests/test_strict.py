"""Strict mode (strict.py): swallowed exceptions re-raise under CASS_STRICT=1."""
import logging

import pytest

from strict import is_strict, report_swallowed


def _swallow(exc):
    try:
        raise exc
    except Exception as e:
        report_swallowed(e, "doing a thing")


def test_conftest_turns_strict_on():
    assert is_strict()


def test_strict_reraises(monkeypatch):
    monkeypatch.setenv("CASS_STRICT", "1")
    with pytest.raises(ValueError, match="boom"):
        _swallow(ValueError("boom"))


def test_non_strict_only_logs(monkeypatch, caplog):
    monkeypatch.setenv("CASS_STRICT", "0")
    with caplog.at_level(logging.ERROR, logger="cass.strict"):
        _swallow(ValueError("boom"))
    assert "doing a thing: boom" in caplog.text


class TestExampleSites:
    """The three places converted as examples. Each used to swallow silently."""

    async def test_action_registry_handler_crash(self, monkeypatch):
        from scheduler.actions import ActionRegistry

        async def broken(context):
            raise AttributeError("no such method")

        registry = ActionRegistry()
        registry.load_definitions()
        registry.register_handler("goals.status", broken)

        with pytest.raises(AttributeError):
            await registry.execute("goals.status")

        monkeypatch.setenv("CASS_STRICT", "0")
        result = await registry.execute("goals.status")
        assert result.success is False and "no such method" in result.message

    async def test_thymos_grimoire_tick_error(self, monkeypatch):
        from thymos import ThymosRunner

        runner = ThymosRunner(daemon_id="strict-test")

        async def broken_hook(affects, needs):
            raise RuntimeError("spell blew up")

        runner._grimoire_on_tick = broken_hook

        async def no_save():
            return None

        monkeypatch.setattr(runner, "_save_state", no_save)
        with pytest.raises(RuntimeError, match="spell blew up"):
            await runner.tick()

        monkeypatch.setenv("CASS_STRICT", "0")
        await runner.tick()  # logged, not raised

    def test_scheduler_event_emit_failure(self, monkeypatch):
        import state_bus
        from scheduler import Synkratos, BudgetManager, BudgetConfig

        def broken_bus(daemon_id):
            raise RuntimeError("bus down")

        monkeypatch.setattr(state_bus, "get_state_bus", broken_bus)
        synkratos = Synkratos(BudgetManager(BudgetConfig()))
        with pytest.raises(RuntimeError, match="bus down"):
            synkratos._emit_scheduler_event("scheduler.test", {})

        monkeypatch.setenv("CASS_STRICT", "0")
        synkratos._emit_scheduler_event("scheduler.test", {})
