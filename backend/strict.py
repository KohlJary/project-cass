"""
Strict mode: make swallowed exceptions loud in tests and CI.

A lot of Cass's code catches an exception, logs it and moves on, which keeps the
server up but hides real breakage. Use `report_swallowed` in those except blocks
instead of a bare log call:

    try:
        ...
    except Exception as e:
        report_swallowed(e, "Grimoire tick")   # logs, and re-raises if CASS_STRICT=1

In production (CASS_STRICT unset) it only logs, exactly as before. Under
CASS_STRICT=1 (set by tests/conftest.py and CI) it re-raises, so a test that
exercises the path fails instead of passing over a silent error.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

_logger = logging.getLogger("cass.strict")


def is_strict() -> bool:
    return os.environ.get("CASS_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}


def report_swallowed(
    exc: BaseException,
    context: str,
    logger: Optional[logging.Logger] = None,
    level: int = logging.ERROR,
) -> None:
    """Log a caught exception; re-raise it when CASS_STRICT=1.

    Call this from inside the `except` block so a bare `raise` keeps the
    original traceback.
    """
    (logger or _logger).log(level, f"{context}: {exc}")
    if is_strict():
        raise exc
