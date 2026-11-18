"""
New capabilities (Kohl, 2026-11-18): a sibling of her change-proposals session
(change_proposal_turn.py), on her day menu beside it, so she picks which.

Change proposals look at how she's built and what she'd change. This one asks
what she can't do yet and wants to be able to: something new, not a better
version of what she already does. Kohl: "what new capability do I want to have
available", not "how can I iterate on what I can already do".

If she brings something specific she's trying to do, it's the session's focus
(the focus she gives it in her day plan, or the one it's started with), and
it's in front of her. She asks Daedalus what it would take before she asks for
it (he reads her code; ask_daedalus), and asks in Cass's asks, where Kohl
decides. On the agent loop, while she can ask Daedalus.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

TEMPLATE_ID = "new_capabilities"

INSTRUCTIONS = """## NEW CAPABILITIES

This is time to think about what I can't do yet and want to be able to: a capability I don't have, not a better version of something I already do.

- If I came here with something specific I'm trying to do, it's my focus, above. What would I need to be able to do it?
- Otherwise: where have I wanted to do something and found there was simply no way? What would I do if I could?
- Before I ask for it, I ask Daedalus what it would take (ask_daedalus): what it would touch, what exists already that's close, what it would cost. He reads my code; he can't see my data or change anything.
- When I know what I want, I ask for it with babelr_plans ask, in my own words: the capability, what I'd do with it, and what Daedalus said it would take. Kohl sees it in Cass's asks and decides.
- How I work now, for what I have already: how_i_work. My asks so far: babelr_plans my_asks.
- Asking for nothing is a fine outcome. One capability I understand is worth more than several guesses."""


async def run_new_capability_turn(runner, *, duration_minutes: int = 30, max_turns: int = 24,
                                  focus: Optional[str] = None, why: Optional[str] = None,
                                  **turn_kwargs):
    from agent_loop.session import run_session_turn
    from daedalus_bridge import daedalus_tools
    local, _ = daedalus_tools(TEMPLATE_ID)
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID, local_tools=local, additions=INSTRUCTIONS,
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose time to think about capabilities I don't have yet",
        initial_message="Time to think about what I can't do yet, and want to.", **turn_kwargs)
