"""The organ keeps trying when Babelr isn't answering yet (2026-11-18 08:14: the vessel
started 7 s before Babelr was back and left her deaf on Babelr until the next restart)."""
import asyncio

import babelr_organ.organ as organ_mod
from babelr_organ.organ import BabelrOrgan, _keep_trying
from tests.fakes.babelr import FakeBabelr
from tests.test_babelr_organ import _config, _place_token


def test_she_comes_back_when_babelr_does(tmp_path, levers, monkeypatch):
    fake = FakeBabelr()
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionRefusedError("Connection refused")
        return fake.make_agent(*a, **kw)

    cfg = _config(tmp_path)
    _place_token(cfg)
    slept = []

    async def no_wait(s):
        slept.append(s)

    async def run():
        with levers(babelr=True):
            organ = BabelrOrgan(config=cfg, client_factory=flaky)
            assert organ.start() is False and organ.disabled_reason.startswith("couldn't reach Babelr")
            monkeypatch.setattr(BabelrOrgan, "run", lambda self: asyncio.sleep(0))
            ok = await _keep_trying(organ, None, sleep=no_wait)
            return organ, ok

    organ, ok = asyncio.run(run())
    assert ok and organ.enabled and slept == [5, 10]
    assert organ_mod.get_babelr_organ() is organ


def test_it_stops_trying_for_what_waiting_wont_fix(tmp_path, levers):
    cfg = _config(tmp_path)
    _place_token(cfg)
    state = {"n": 0}

    def gone_token(*a, **kw):
        state["n"] += 1
        raise ConnectionRefusedError("refused")

    async def no_wait(s):
        cfg.token_file.unlink(missing_ok=True)   # now the token is missing: no point waiting

    async def run():
        with levers(babelr=True):
            organ = BabelrOrgan(config=cfg, client_factory=gone_token)
            organ.start()
            return await _keep_trying(organ, None, sleep=no_wait)

    assert asyncio.run(run()) is False
