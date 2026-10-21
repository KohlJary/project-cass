"""
The one clock Heartbeat runs on.

`SystemClock` reads the same zone as cron (schedule_clock.cron_now: the
CASS_TIMEZONE zone when set, else UTC), so every Heartbeat cadence is measured
on one clock. `FakeClock` is for tests: time only moves when the test moves it.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional


class SystemClock:
    def now(self) -> datetime:
        from schedule_clock import cron_now
        return cron_now()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FakeClock:
    """A clock tests drive by hand. sleep() advances time and yields once."""

    def __init__(self, start: Optional[datetime] = None):
        self._now = start or datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float = 0, **kwargs) -> datetime:
        self._now += timedelta(seconds=seconds, **kwargs)
        return self._now

    def set(self, when: datetime) -> None:
        self._now = when

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)
        await asyncio.sleep(0)
