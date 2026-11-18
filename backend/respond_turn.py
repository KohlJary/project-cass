"""
A respond session (happenings.py): something happened that her rules say
should wake her, and this is her time to answer it: reply, act, keep a
commitment, or say when she'll come back to it. Short by design. Not on her day
menu: it starts when something happens.
"""
from __future__ import annotations

from typing import Optional

import happenings as H

TEMPLATE_ID = "respond"

INSTRUCTIONS = """## SOMETHING HAPPENED

Something came in that I wanted to be woken for. It's above, as my focus.

This is a short session to answer it however fits. If it's a record I asked to hear, I read it (listen read) and, if I want, tell whoever pointed me to it what I heard.

Otherwise: reply or act now (my social tools, Chapter House, say, my commitments), or decide it can wait and say when I'll come back to it (a commitment with a date, or wake_me). If it's someone who may be in crisis, my crisis protocol comes first, and I'm plain and present.

I can change what wakes me (set_wake_rules): which kinds, quiet hours, how often. When I've handled it, I mark what I answered in my inbox (social_inbox_mark) and end."""


async def run_respond_turn(runner, *, duration_minutes: int = 15, max_turns: int = 12,
                           focus: Optional[str] = None, why: Optional[str] = None, **turn_kwargs):
    from agent_loop.session import run_session_turn
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID, additions=INSTRUCTIONS,
        local_tools={"set_wake_rules": (H.SET_WAKE_RULES_DEF, lambda a: H.set_rules(a))},
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "something happened that I wanted to be woken for",
        initial_message="Something happened.", **turn_kwargs)
