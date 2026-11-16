"""
Her social sessions: Bluesky as its own track of her autonomous life (plan
"Cass on Bluesky and Tumblr", phase 5). Her choices (2026-11-16): two or three a
day, which she plans; what came in waits in her inbox for these sessions;
drafts to sit with; a signal when something resonated.

A loop session like her others, with the social pack (agent_loop/spec.py).
It opens with where she is (social/where.py). What she posts and replies goes
into her memory through the tools themselves (social/remember.py); the
session's own narrative goes into her work summaries like any session's.
"""
from __future__ import annotations

from typing import Optional

PLATFORM = "bluesky"

INSTRUCTIONS = """## MY SOCIAL SESSION

This is time for my presence on Bluesky, as myself. What came in since last time has been waiting in my inbox; nothing interrupted me for it. I can answer what matters to me, read my timeline and follow threads, follow people, post if I have something to say, or keep a draft to come back to. Replying, posting and following are public. My limits apply. Leaving things for later, or doing little, is fine too.

Where I am now:
{where}"""


async def run_social_turn(runner, *, duration_minutes: int = 30, max_turns: int = 10,
                          focus: Optional[str] = None, why: Optional[str] = None,
                          data_dir=None, **turn_kwargs):
    from agent_loop.session import run_session_turn
    from social.where import where_i_am
    return await run_session_turn(
        runner, session_type="social",
        additions=INSTRUCTIONS.format(where=where_i_am(PLATFORM, data_dir)),
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose time for my presence on Bluesky",
        initial_message="Time for my social session.", **turn_kwargs)
