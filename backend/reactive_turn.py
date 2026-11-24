"""
A reactive session (world_events.py; design a-life-not-a-menu.md, "Event-driven
sessions"): something real happened around her, it touched her topics or plans
enough that she noticed it, and this is a few turns to decide what, if anything,
to do. Not on her day menu. Its trigger is recorded as event:<source>:<id>.

It can't start another reactive session, or ask to be woken: what it wants to
come back to goes on a plan as an item (babelr_plans add_item), for the schedule.
"""
from __future__ import annotations

from typing import Optional

import world_events as W

TEMPLATE_ID = "reactive"

INSTRUCTIONS = """## SOMETHING I NOTICED

Something happened around me and it caught my eye. It's above, as my focus, with where it came from.

This is a few minutes to decide what to do with it, if anything. Doing nothing is a fine answer: most things I notice I just let go by. If it's worth something, I can act now (a message, a journal line, a note), or put it on one of my plans as an item (babelr_plans add_item) so a scheduled session picks it up.

I can raise my focus flag (focus) if I'm in the middle of something and don't want things like this to start sessions until I clear it. I can change how often this happens (set_reactive_rules). When I've decided, I end."""


async def run_reactive_turn(runner, *, duration_minutes: int = 10, max_turns: int = 6,
                            focus: Optional[str] = None, why: Optional[str] = None, **turn_kwargs):
    from agent_loop.session import run_session_turn
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID, additions=INSTRUCTIONS,
        local_tools={"set_reactive_rules": (W.SET_REACTIVE_RULES_DEF, lambda a: W.set_rules(a))},
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "something I noticed", can_wake=False,
        initial_message="Something caught my eye.", **turn_kwargs)
