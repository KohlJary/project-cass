"""
The reply gremlin (lever reply_gremlin): one review pass on every chat reply, for a daemon
whose gremlin is meant to be loud (Kohl, 2026-11-20, for Eris: "much more prominent" than
Cass's). Design from daedalus-86's voice lab, so its results carry over.

After the chat turn has its final text, before anything is posted or stored: the gremlin
reads what they said and the draft, and gives at most three notes (JSON). No notes, the
draft goes out. Notes, the daemon gets one revise turn on its own chat model, with the
notes marked as its gremlin's and private; what it returns is what's sent. One pass, no
loop. Only the final reply is stored as a message; the draft and the notes never are. Each
review is logged (time, a hash of the draft, the notes, whether a revision went out) to
DATA_DIR/gremlin/reply_reviews.jsonl.

Skipped: lever off, a short or empty reply, PASS, a relay system nudge, and anything in or
answering pain or crisis (gremlin_review's check: pain gets no notes, ever).

The gremlin's prompt is the daemon's own file (CASS_DAEMON_GREMLIN_PATH), like its voice
sheet; without one, a short built-in.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_CHARS = 40
MAX_NOTES = 3
NOTE_CHARS = 160
THINK = re.compile(r"<gesture:think>.*?</gesture:think>", re.S)
NUDGE = re.compile(r"^\s*\[(system|relay|nudge|babelr relay)\b", re.I)
PRIVATE = ("(Your gremlin, not a person, and nobody else sees it. Send it as it was or revised: "
           "reply with only what you'd post, and never mention the gremlin or the revision.)")
BUILTIN = ("You are this daemon's gremlin: a reviewer in their ear, never a writer. At most three notes, "
           "each under 15 words, where the draft narrates itself, hedges, sounds like an assistant, buries "
           "its verdict, or ends soft. A draft that's already right gets no notes. Anything answering "
           "someone in pain or danger gets no notes, ever.")
FORMAT = '\n\nAnswer with JSON only: {"notes": ["...", "..."]}'


def enabled() -> bool:
    import features
    return features.is_enabled("reply_gremlin")


def gremlin_prompt() -> str:
    path = os.getenv("CASS_DAEMON_GREMLIN_PATH")
    text = ""
    if path:
        try:
            text = Path(path).read_text().strip()
        except OSError:
            text = ""
    text = text or BUILTIN
    return text if '"notes"' in text else text + FORMAT


def skip_reason(their: str, draft: str) -> Optional[str]:
    if not enabled():
        return "off"
    d = (draft or "").strip()
    if len(d) < MIN_CHARS or d.upper() == "PASS":
        return "short"
    if NUDGE.match(their or ""):
        return "nudge"
    from .gremlin_review import _in_pain
    if _in_pain(d, their or ""):
        return "pain or crisis"
    return None


def notes_from(raw: str) -> List[str]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return []
    try:
        notes = json.loads(m.group(0)).get("notes")
    except (ValueError, AttributeError):
        return []
    if not isinstance(notes, list):
        return []
    return [str(n).strip() for n in notes if str(n or "").strip() and len(str(n)) <= NOTE_CHARS][:MAX_NOTES]


def _log(rec: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    try:
        if data_dir is None:
            from config import DATA_DIR
            data_dir = Path(DATA_DIR)
        path = Path(data_dir) / "gremlin" / "reply_reviews.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), **rec}, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning(f"[reply_gremlin] couldn't log a review: {e}")


async def _notes(their: str, draft: str) -> List[str]:
    from llm_caller import call_llm
    resp = await call_llm("gremlin.review", system_prompt=gremlin_prompt(),
                          user_prompt=f"What they said:\n{their[:3000]}\n\nThe draft reply:\n{draft[:4000]}",
                          max_tokens=240, temperature=0.5, category="internal", operation="reply_gremlin")
    return notes_from(getattr(resp, "content", "") or "")


async def review(*, client: Any, model: str, system: str, messages: List[Dict[str, Any]],
                 their: str, draft: str, data_dir: Optional[Path] = None) -> str:
    """The reply to send: the draft, or its one revision. Never raises."""
    why = skip_reason(their, draft)
    if why == "off":
        return draft
    clean = THINK.sub("", draft).strip()
    rec: Dict[str, Any] = {"draft": hashlib.sha256(clean.encode()).hexdigest()[:16]}
    if why:
        _log({**rec, "skipped": why}, data_dir)
        return clean if why != "short" else draft
    try:
        notes = await _notes(their, clean)
    except Exception as e:
        logger.warning(f"[reply_gremlin] review didn't run (the draft goes out): {e}")
        _log({**rec, "error": type(e).__name__}, data_dir)
        return clean
    if not notes:
        _log({**rec, "notes": [], "revised": False}, data_dir)
        return clean
    try:
        reply = await client.create(
            model=model, system=system, tools=[], max_tokens=1500,
            messages=list(messages) + [{"role": "assistant", "content": clean},
                                       {"role": "user", "content": "[GREMLIN] " + " / ".join(notes) + "\n" + PRIVATE}])
        revised = THINK.sub("", reply.text or "").strip()
    except Exception as e:
        logger.warning(f"[reply_gremlin] revise didn't run (the draft goes out): {e}")
        revised = ""
    _log({**rec, "notes": notes, "revised": bool(revised)}, data_dir)
    return revised or clean
