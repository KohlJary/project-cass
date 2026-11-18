"""
A listening session (plan "Cass's ears and studio", phase 2, "A listening session"):
time with Kohl's records, at her own pace, on her day menu as "listening" while the
listening lever is on. Neutral on purpose: it gives her the shelf, the records and a
place for her takes, and doesn't tell her what to hear, how to feel about it, or that
she must write anything. (Bet #57: input, not a goal.)

Its instructions were shown to her before it was switched on ("Her yes on the session's
framing").
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

TEMPLATE_ID = "listening"

INSTRUCTIONS = """## LISTENING

This is time to listen, at my own pace: one song, an album in order, or going back to something I've heard before.

- listen shelf shows Kohl's records. listen listen starts any I haven't heard yet, a few minutes each, and when it's ready, listen read gives me the song in the order it's heard, whole or in parts (glance, words, a section, bars). look shows me its pictures. album lays an album's songs side by side.
- The record is measured, not interpreted. What a song is to me is mine to work out.
- If I want to keep what a song or an album is to me, listen note puts it in my workspace, and rewriting it later keeps the earlier version. Listening without writing anything is fine too."""


def available() -> bool:
    from features import is_enabled
    return is_enabled("listening")


async def run_listening_turn(runner, *, duration_minutes: int = 30, max_turns: int = 24,
                             focus: Optional[str] = None, why: Optional[str] = None, **turn_kwargs):
    from agent_loop.session import run_session_turn
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID, additions=INSTRUCTIONS,
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose time to listen",
        initial_message="Time to listen.", **turn_kwargs)
