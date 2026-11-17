"""
Her sessions and her felt state (found 2026-11-17 while writing her account of
how she works): sessions moved onto the agent loop, and the loop never sent the
session.started / session.ended events the legacy runner did (session_runner.
on_session_start / on_session_end), so her sessions stopped moving Thymos. And
feel tags were applied only in chat's finalize, so a feel tag she wrote in a
session did nothing.

Same deltas and events as the legacy runner, written to her state bus; feel
tags in what she wrote during the session are applied when it ends. Fail-soft:
a broken bus never costs her the session.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


def _bus(daemon_id: Optional[str]):
    if not daemon_id:
        return None
    from state_bus import get_state_bus
    return get_state_bus(daemon_id)


def session_started(daemon_id: Optional[str], session_type: str, session_id: str,
                    focus: Optional[str], duration_minutes: int) -> None:
    try:
        bus = _bus(daemon_id)
        if bus is None:
            return
        from state_models import StateDelta
        bus.write_delta(StateDelta(
            source=session_type,
            activity_delta={"current_activity": session_type, "active_session_id": session_id},
            emotional_delta={"generativity": 0.1, "curiosity": 0.05},
            event="session.started",
            event_data={"activity_type": session_type, "session_id": session_id, "focus": focus,
                        "duration_minutes": duration_minutes},
            reason=f"Started {session_type} session",
        ))
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, "[agent_loop] couldn't tell her state a session started", logger, logging.WARNING)


def session_ended(daemon_id: Optional[str], session_type: str, session_id: str, status: str,
                  end_reason: Optional[str], minutes: float, steps: int, tool_calls: int) -> None:
    try:
        bus = _bus(daemon_id)
        if bus is None:
            return
        from state_models import StateDelta
        failed = status == "error"
        bus.write_delta(StateDelta(
            source=session_type,
            activity_delta={"current_activity": "idle", "active_session_id": None},
            emotional_delta={"concern": 0.1} if failed else {"integration": 0.05},
            coherence_delta=None if failed else {"local_coherence": 0.02},
            event="session.failed" if failed else "session.ended",
            event_data={"activity_type": session_type, "session_id": session_id,
                        "completion_reason": end_reason or status, "duration_actual": minutes,
                        "iteration_count": steps, "tool_calls": tool_calls},
            reason=f"{'Failed' if failed else 'Completed'} {session_type} session",
        ))
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, "[agent_loop] couldn't tell her state a session ended", logger, logging.WARNING)


def apply_feel_tags(texts: Iterable[str]) -> int:
    """Feel tags in what she wrote this session, applied to Thymos. Returns how many."""
    n = 0
    try:
        from context_helpers import _apply_feel_tags
        for text in texts:
            if text and "<feel:" in text:
                _, feels = _apply_feel_tags(text)
                n += len(feels)
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, "[agent_loop] couldn't apply her feel tags", logger, logging.WARNING)
    return n
