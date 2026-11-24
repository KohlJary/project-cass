"""Her Ollama calls behind the GPU broker (gpu_broker_client.llm_lease, 2026-11-24)."""
import asyncio
import contextlib

import pytest

import gpu_broker_client as gbc


class FakeSessions:
    def __init__(self, fail=False):
        self.entered = 0
        self.exited = 0
        self.fail = fail

    def __call__(self, model, idle_min=2.0, max_wait=300.0):
        outer = self

        @contextlib.asynccontextmanager
        async def cm():
            if outer.fail:
                raise gbc.BrokerError("timed out")
            outer.entered += 1
            try:
                yield "job"
            finally:
                outer.exited += 1
        return cm()


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(gbc, "enabled", lambda: True)
    monkeypatch.setattr(gbc, "GRACE_S", 0.05)
    monkeypatch.setattr(gbc, "SESSIONS_FOR_LLM", True)  # the session path, behind its switch


def test_concurrent_calls_share_one_session_released_after_grace(on):
    fake = FakeSessions()
    lease = gbc._LLMLease(session=fake)

    async def call():
        async with lease.hold():
            await asyncio.sleep(0.02)

    async def main():
        await asyncio.gather(call(), call(), call())
        assert fake.entered == 1 and fake.exited == 0, "held through the grace period"
        await asyncio.sleep(0.1)
        assert fake.exited == 1
        await call()  # a later call opens a fresh one
        assert fake.entered == 2
    asyncio.run(main())


def test_a_call_inside_the_grace_period_reuses_the_session(on):
    fake = FakeSessions()
    lease = gbc._LLMLease(session=fake)

    async def main():
        async with lease.hold():
            pass
        async with lease.hold():
            pass
        await asyncio.sleep(0.1)
        assert fake.entered == 1 and fake.exited == 1
    asyncio.run(main())


def test_no_card_in_time_is_an_error_not_a_silent_call(on):
    lease = gbc._LLMLease(session=FakeSessions(fail=True))

    async def main():
        with pytest.raises(gbc.BrokerError):
            async with lease.hold():
                pytest.fail("called without the card")
    asyncio.run(main())


def test_lever_off_is_a_no_op(monkeypatch):
    monkeypatch.setattr(gbc, "enabled", lambda: False)
    fake = FakeSessions()
    lease = gbc._LLMLease(session=fake)

    async def main():
        async with lease.hold():
            pass
    asyncio.run(main())
    assert fake.entered == 0


def test_sync_callers_wait_out_an_image_or_song_session(on):
    states = [{"session": {"model": "comfyui"}}, {"session": {"model": "comfyui"}}, {"session": None}]
    slept = []
    gbc.wait_for_llm_sync(max_wait=60, sleep=slept.append, get=lambda: states.pop(0))
    assert len(slept) == 2


def test_sync_callers_dont_wait_for_an_llm_session_and_give_up_eventually(on):
    gbc.wait_for_llm_sync(max_wait=60, sleep=lambda s: None, get=lambda: {"session": {"model": "llama31"}})
    t = iter(range(0, 10_000, 100))
    import time as _time
    real = _time.monotonic
    try:
        gbc.time.monotonic = lambda: next(t)
        with pytest.raises(gbc.BrokerError):
            gbc.wait_for_llm_sync(max_wait=150, sleep=lambda s: None,
                                  get=lambda: {"session": {"model": "acestep"}})
    finally:
        gbc.time.monotonic = real


def test_an_unreachable_broker_doesnt_stop_her_thinking(on):
    def boom():
        raise OSError("refused")
    gbc.wait_for_llm_sync(max_wait=60, sleep=lambda s: None, get=boom)


def test_by_default_her_calls_wait_out_an_image_session_instead_of_opening_one(monkeypatch):
    monkeypatch.setattr(gbc, "enabled", lambda: True)
    monkeypatch.setattr(gbc, "SESSIONS_FOR_LLM", False)
    monkeypatch.setattr(gbc, "POLL_S", 0.0)
    fake = FakeSessions()
    lease = gbc._LLMLease(session=fake)
    states = [{"session": {"model": "comfyui"}}, {"session": None}]
    real = gbc.wait_for_llm

    async def waited(max_wait=None, get=None):
        await real(max_wait=60, get=lambda: states.pop(0))
    monkeypatch.setattr(gbc, "wait_for_llm", waited)

    async def main():
        async with lease.hold():
            pass
    asyncio.run(main())
    assert fake.entered == 0 and states == []
