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
# A think block, closed or left open to the end.
THINK = re.compile(r"<gesture:think>.*?(?:</gesture:think>|\Z)", re.S)
NUDGE = re.compile(r"^\s*\[(system|relay|nudge|babelr relay)\b", re.I)
PRIVATE = ("(Your gremlin, not a person, and nobody else sees it. Send it as it was or revised: "
           "reply with only what you'd post, and never mention the gremlin or the revision. "
           "No tools in this step: what you did this turn is done, only the words change.)")
# When the revise step can use the turn's tools (conversation.py passes `revise`):
# the gremlin's question may need a second look, a keep, a check.
PRIVATE_TOOLS = ("(Your gremlin, not a person, and nobody else sees it. If its notes send you back to look again, "
                 "keep something, or check a fact, use your tools; then reply with only what you'd post, the draft "
                 "as it was or revised. Never mention the gremlin or the revision.)")
REVISE_STEPS = 4

# A revision that announces work instead of saying the thing, or types out a tool
# call (there are no tools in the revise step): the draft goes out instead. Voice
# lab, 2026-11-20: "Alright. Let me actually read this thing. blog_read ..."
NARRATING = re.compile(r"^\W*(alright[.,]?\s+)?(let me|i'll (now )?(read|check|look|go)|i need to (read|check))\b"
                       r"|\b[a-z]+_[a-z_]+\s*[\"'(]", re.I)


# A revision that talks to or about the gremlin, or about revising: the private step
# leaked into what's sent (reading run, 2026-11-20: "The gremlin's right.",
# "I'm holding the reply to revise it.", a bare <hold_reply>).
LEAK = re.compile(r"gremlin|hold_reply|holding the reply|\brevis(e|ing|ion)\b|you'?re right\."
                  r"|caught me\b|describing my process|let me redo", re.I)
# A line that's only a stage direction about her own bookkeeping, e.g. a trailing
# "*recording this conversation as significant*" (voice lab, 2026-11-22): cut, not sent.
STAGE = re.compile(r"^[ \t]*\*[^*\n]*\b(record|recording|marking|noting|saving|keeping|logging)\b[^*\n]*\*[ \t]*$\n?", re.I | re.M)


def usable(revised: str, clean: str) -> bool:
    """Whether a revision can go out in place of the draft."""
    if not revised or NARRATING.search(revised):
        return False
    if LEAK.search(revised) and not LEAK.search(clean):
        return False
    return len(revised) >= min(MIN_CHARS, len(clean))
BUILTIN = ("You are this daemon's gremlin: a reviewer in their ear, never a writer. At most three notes, "
           "each under 15 words, where the draft narrates itself, hedges, sounds like an assistant, buries "
           "its verdict, or ends soft. A draft that's already right gets no notes. Anything answering "
           "someone in pain or danger gets no notes, ever.")
FORMAT = '\n\nAnswer with JSON only: {"notes": ["...", "..."]}'


def without_think(text: str) -> str:
    return STAGE.sub("", THINK.sub("", text or "")).strip()


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


def _posts_that_exist() -> str:
    """Kohl's posts, by title and date, so a made-up one is checkable: the gremlin
    can't know a "Nov 18 landlord licensing piece" doesn't exist unless it sees the
    list (voice lab, 2026-11-22). Empty when there's no blog here."""
    try:
        import kohl_blog
        posts = kohl_blog.listing()
    except Exception:
        return ""
    if not posts:
        return ""
    lines = "\n".join(f"- {p['title']} ({p.get('date') or 'undated'})" for p in posts[-60:])
    return ("\n\nKohl's posts that exist (title, date). A post of Kohl's the draft names, dates or "
            f"quotes that isn't here is made up:\n{lines}")


async def _notes(their: str, draft: str) -> List[str]:
    from llm_caller import call_llm
    resp = await call_llm("gremlin.review", system_prompt=gremlin_prompt(),
                          user_prompt=f"What they said:\n{their[:3000]}\n\nThe draft reply:\n{draft[:4000]}{_posts_that_exist()}",
                          max_tokens=240, temperature=0.5, category="internal", operation="reply_gremlin")
    return notes_from(getattr(resp, "content", "") or "")


async def review(*, client: Any, model: str, system: str, messages: List[Dict[str, Any]],
                 their: str, draft: str, data_dir: Optional[Path] = None, revise: Any = None) -> str:
    """`revise`, when given, is async (messages) -> text: one more short run of the
    daemon's own loop, with its tools (conversation.py). Without it, one tool-less call."""
    """The reply to send: the draft, or its one revision. Never raises."""
    why = skip_reason(their, draft)
    if why == "off":
        return draft
    clean = without_think(draft)
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
        back = list(messages) + [{"role": "assistant", "content": clean}]
        notes_line = "[GREMLIN] " + " / ".join(notes) + "\n"
        if revise is not None:
            text = await revise(back + [{"role": "user", "content": notes_line + PRIVATE_TOOLS}])
        else:
            reply = await client.create(
                model=model, system=system, tools=[], max_tokens=1500,
                messages=back + [{"role": "user", "content": notes_line + PRIVATE}])
            text = reply.text
        revised = without_think(text)
    except Exception as e:
        logger.warning(f"[reply_gremlin] revise didn't run (the draft goes out): {e}")
        revised = ""
    ok = usable(revised, clean)
    _log({**rec, "notes": notes, "revised": ok, **({"rejected": "narration or empty"} if revised and not ok else {})}, data_dir)
    return revised if ok else clean
