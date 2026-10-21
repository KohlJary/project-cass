"""
One agent loop for every turn (epic #70, docs/design/agent-loop.md).

Built beside the old code behind the lever `agent_loop` (off by default).
So far only autonomous sessions run through it (agent_loop.session); chat,
dreams, journals and the memory writers still use their own paths.

  spec.py       TurnSpec per kind: tool packs, write policy, cap, budget rules
  seam.py       the "THIS MOMENT" block, rendered from the spec
  assemble.py   assemble(): the one system-prompt builder for a turn
  loop.py       ModelClient interface + the one capped tool loop, guarded writes
  interrupt.py  has a conversation arrived since the turn began?
  session.py    autonomous sessions as Turns
"""
from .spec import PACKS, Trigger, TurnSpec, session_spec  # noqa: F401
from .seam import render_seam  # noqa: F401
