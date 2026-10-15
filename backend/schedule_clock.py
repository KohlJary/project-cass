"""
One clock for time-of-day scheduling.

Synkratos cron jobs used UTC while day phases used the server's local time.
Set CASS_TIMEZONE (config.py) to make both use the same zone. Unset, each
keeps its old clock, so nothing moves unless you opt in.
"""
from datetime import datetime, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo


def configured_timezone() -> Optional[tzinfo]:
    """The CASS_TIMEZONE zone, or None when it isn't set."""
    import config
    name = getattr(config, "CASS_TIMEZONE", None)
    return ZoneInfo(name) if name else None


def cron_now() -> datetime:
    """Now, on the clock cron expressions are written in (aware datetime)."""
    tz = configured_timezone()
    return datetime.now(tz or timezone.utc)


def phase_now() -> datetime:
    """Now, on the clock day phases are measured in.

    Unset: naive server-local time, exactly as before.
    """
    tz = configured_timezone()
    return datetime.now(tz) if tz else datetime.now()
