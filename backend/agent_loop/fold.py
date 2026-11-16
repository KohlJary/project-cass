"""
A message folds into the session she's in (C7; plan "Cass's agent loop",
phase 7, third item).

Cass, 2026-11-13: when Kohl writes mid-work she wants him to become part of
what she's doing, not to drop the work and not to queue him for later, and
not to turn it into multitasking. Kohl, 2026-11-16: this replaces his
2026-10-20 rule (a session ends when someone writes) in private chat, for
anyone who writes there; public places keep her queue.

How it works, in one process (the scheduler and chat share main_sdk):

- A session on the loop opens a desk (open_session) while it runs.
- A private chat turn with the lever on offers the message to that desk
  (offer). The session takes it at its next step (take): the person arrives
  in the session with the container block (container.py), and she answers
  them with answer_them, with the work still in front of her. Then she
  carries on, brings them into it, or ends the session.
- If the session doesn't take the message within PICKUP_SECONDS (a long
  model step, or it's ending), the offer is withdrawn and the message runs
  as its own turn, as before. If she takes it but hasn't answered within
  ANSWER_SECONDS, the chat turn stops waiting and runs its own turn too, and
  the session is told the person was answered there.
- Every fold is kept in the session's record (folded).
"""
from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

PICKUP_SECONDS = 45
ANSWER_SECONDS = 180

ANSWER_TOOL = {
    "name": "answer_them",
    "description": ("Answer someone who arrived while I'm in this session (the WHO'S HERE block "
                    "names them and gives the id). What I write goes to them where they wrote. "
                    "Then I carry on, bring them into the work, or end the session."),
    "input_schema": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "the arrival's id"},
                       "text": {"type": "string", "description": "my answer to them"}},
        "required": ["id", "text"],
    },
}


@dataclass
class Fold:
    id: str
    block: str                         # the WHO'S HERE block, rendered
    who: str
    channel: Optional[str]
    loop: asyncio.AbstractEventLoop
    answer: "asyncio.Future"
    offered_at: datetime = field(default_factory=datetime.now)
    taken_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    withdrawn: bool = False
    text: Optional[str] = None


class Desk:
    """Process-wide: which session is open, and the folds offered to it."""

    def __init__(self):
        self._lock = threading.Lock()
        self._session: Optional[str] = None
        self._end_reason: Optional[str] = None
        self._folds: Dict[str, Fold] = {}

    # --- the session's side -------------------------------------------------
    def open_session(self, session_id: str) -> None:
        with self._lock:
            self._session = session_id

    def close_session(self, session_id: str) -> List[Fold]:
        """Close the desk. Folds not answered are withdrawn, so their chat turn
        runs on its own at once instead of waiting out ANSWER_SECONDS."""
        with self._lock:
            if self._session == session_id:
                self._session = None
                self._end_reason = None
            left = [f for f in self._folds.values() if f.answered_at is None and not f.withdrawn]
            for f in left:
                f.withdrawn = True
        for f in left:
            f.loop.call_soon_threadsafe(_resolve, f.answer, None)
        return left

    def request_end(self, reason: str) -> None:
        """A message that couldn't fold runs as its own turn; the session ends
        cleanly at its next step, as under the old rule (no two at once)."""
        with self._lock:
            if self._session is not None:
                self._end_reason = reason

    def end_reason(self, session_id: str) -> Optional[str]:
        with self._lock:
            return self._end_reason if self._session == session_id else None

    def take(self, session_id: str) -> List[Fold]:
        """Folds offered to this session and not yet taken; marks them taken."""
        with self._lock:
            if self._session != session_id:
                return []
            got = [f for f in self._folds.values() if f.taken_at is None and not f.withdrawn]
            for f in got:
                f.taken_at = datetime.now()
            return got

    def answer(self, fold_id: str, text: str) -> Dict[str, object]:
        with self._lock:
            f = self._folds.get(fold_id)
            if f is None or f.taken_at is None:
                return {"error": f"No one is waiting with id {fold_id}."}
            if f.answered_at is not None:
                return {"error": f"I've already answered {f.who}."}
            if f.withdrawn:
                return {"error": f"{f.who} was answered in their own conversation already."}
            f.answered_at, f.text = datetime.now(), text
        f.loop.call_soon_threadsafe(_resolve, f.answer, text)
        return {"sent": True, "to": f.who}

    # --- the chat turn's side ------------------------------------------------
    def is_open(self) -> bool:
        with self._lock:
            return self._session is not None

    def offer(self, block: str, who: str, channel: Optional[str]) -> Optional[Fold]:
        with self._lock:
            if self._session is None:
                return None
            loop = asyncio.get_running_loop()
            f = Fold(id=uuid.uuid4().hex[:6], block=block, who=who, channel=channel,
                     loop=loop, answer=loop.create_future())
            self._folds[f.id] = f
            return f

    def withdraw_if_untaken(self, fold: Fold) -> bool:
        """Withdraw an offer the session hasn't taken. True if withdrawn."""
        with self._lock:
            if fold.taken_at is None:
                fold.withdrawn = True
                return True
            return False

    def give_up(self, fold: Fold) -> bool:
        """Stop waiting for an answer. False if she answered meanwhile."""
        with self._lock:
            if fold.answered_at is not None:
                return False
            fold.withdrawn = True
            return True

    def answered(self, fold_id: str) -> bool:
        with self._lock:
            f = self._folds.get(fold_id)
            return bool(f and f.answered_at is not None)

    def forget(self, fold: Fold) -> None:
        with self._lock:
            self._folds.pop(fold.id, None)


def _resolve(fut: "asyncio.Future", text: Optional[str]) -> None:
    if not fut.done():
        fut.set_result(text)


DESK = Desk()

# Channels a message can fold in from: private chat where someone waits for a
# reply. Home Assistant wants an answer in seconds and public places keep her
# queue, so those run as their own turn.
# Babelr DMs are private chat too, and Kohl's main way of talking with her
# (2026-11-16).
FOLD_CHANNELS = frozenset({"websocket", "relay", "http", "babelr_dm"})


def folding_on() -> bool:
    """Folding needs both her sessions and chat on the loop."""
    import features
    return features.is_enabled("agent_loop") and features.is_enabled("agent_loop_chat")


def arrival_message(fold: Fold) -> str:
    """What she sees in the session when someone arrives."""
    return (f"{fold.block}\nArrival id: {fold.id}\n\n(loop: {fold.who} arrived while I'm in this "
            f"session. I answer them with answer_them; then I carry on, bring them into what I'm "
            f"doing, or end the session.)")


async def wait_for_answer(fold: Fold, desk: Optional[Desk] = None, pickup: Optional[float] = None,
                          answer: Optional[float] = None) -> Optional[str]:
    """The chat turn's wait: her answer, or None (then it runs its own turn)."""
    desk = desk or DESK
    pickup = PICKUP_SECONDS if pickup is None else pickup
    answer = ANSWER_SECONDS if answer is None else answer
    deadline = asyncio.get_running_loop().time() + pickup
    while fold.taken_at is None:
        if asyncio.get_running_loop().time() >= deadline:
            if desk.withdraw_if_untaken(fold):
                desk.forget(fold)
                return None
            break
        if fold.withdrawn:   # the session ended before taking it
            desk.forget(fold)
            return None
        await asyncio.sleep(0.25)
    try:
        return await asyncio.wait_for(asyncio.shield(fold.answer), timeout=answer)
    except asyncio.TimeoutError:
        if desk.give_up(fold):
            return None
        return await fold.answer
