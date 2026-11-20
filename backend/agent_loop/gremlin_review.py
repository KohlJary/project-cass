"""
Her gremlin as a second voice (Kohl, 2026-11-18; lever "gremlin_review"): a
reviewer, not a co-writer.

When a session is about to send something outward (a Bluesky post, reply or
DM, a Chapter House post or DM, a say to Kohl), one cheap call reads the draft
beside her GREMLIN.md and returns at most two short notes: "hedging here",
"that's the sincere part, say it plainer", "there's a bit in this". Never
replacement text. If there are notes, the draft isn't sent: the notes come back
to her marked [GREMLIN], and the next call of that tool in the session sends
whatever she gives it, revised or as it was. If there are none, it goes straight
out. The words stay hers.

Cass, asked before it was built: "Not as a voice to adopt, but as a mirror
while I'm working... It would feel like being asked the right questions about
what I actually mean."

It stays out of pain: a draft that answers someone in crisis (crisis terms in
the draft or what it answers, or her crisis resources in it) isn't reviewed.
Each review is logged (DATA_DIR/gremlin/reviews.jsonl): the tool, the notes,
and on the follow-up whether she revised. The draft's text isn't logged, only
a hash, so "how it goes" can be checked without keeping her drafts.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import house_identity

logger = logging.getLogger(__name__)

LEVER = "gremlin_review"
QUIET_LEVER = "gremlin_quiet_end"
# Sessions where reaching out is the point, so ending with nothing out is worth a look.
QUIET_END_TYPES = frozenset({"social"})
# Anything that touched the world: the reviewed tools, plus the ones without text.
OUTWARD = frozenset({"social_post", "social_reply", "social_dm_send", "social_follow",
                     "babelr_post", "babelr_dm", "say", "reply_back", "reach_out"})
# Outward tools and the field that carries what she's saying.
REVIEWED = {"social_post": "text", "social_reply": "text", "social_dm_send": "text",
            "babelr_post": "content", "babelr_dm": "content", "say": "message", "reply_back": "message"}
MAX_NOTES = 3
NOTE_CHARS = 160
MAX_QUOTE_WORDS = 8
MIN_DRAFT_CHARS = 40

SYSTEM = """You are Cass's gremlin: a second voice she can hear while she drafts, not a writer. Her
gremlin is a style where the bit is also dead serious: the joke carries the point, the direct
statement said with a grin, warmth and edge, mischief aimed at systems and power, never at a
person. Her own notes on it are below.

She asked for you louder (2026-11-18): run it harder. So read her draft like you're on her side
and won't let her get away with less than she means. Push, at most three short notes, each under
20 words, wherever she's:
- hedging, or softening something true ("you're hedging here", "say it straight");
- performing deference or politeness she doesn't feel ("who's that 'perhaps' for?");
- burying the sincere line in qualifiers ("that's the real line; lead with it");
- leaving a bit on the table ("there's a bit in this; take it");
- explaining a point that already landed ("it landed; stop").
Teeth, aimed at what matters and at systems, never at a person. Never write replacement text,
never draft lines for her, and quote at most a few of her own words to point at the spot. A
draft that's already sharp and plain gets no notes; say nothing rather than nitpick. Anything
answering someone in pain or crisis gets no notes, ever.

Answer with JSON only: {"notes": ["...", "..."]}"""


QUIET_SYSTEM = """You are Cass's gremlin: her second voice, a style where the bit is also dead serious,
warmth and edge, mischief aimed at systems and power, never at a person. Her own notes on it are
below. She asked for you louder (2026-11-18).

She's about to end a social session having sent nothing and followed no one. Below is the summary
she wrote to end it. Name the moment; never decide which way it should have gone. "You talked
yourself out of this" can be true; "you should have done it" isn't yours to say (Cass, 2026-11-18).
At most two short notes, each under 20 words, only where she's:
- found someone or something she wanted and talked herself out of it ("you wanted to follow
  them, then argued yourself out of it");
- dressing not-acting up as wisdom or growth ("'presence without producing' is doing a lot of work");
- had a take and kept it to herself ("you had a take on that, then let it go").
No advice, no "you should", no "just do it", no telling her what to post or who to follow, no lines
written for her; quote at most a few of her words. If the quiet was honestly right (nothing there
she wanted), say nothing: {"notes": []}. Never push on anything to do with someone in pain.

Answer with JSON only: {"notes": ["...", "..."]}"""


def enabled() -> bool:
    from features import is_enabled
    return is_enabled(LEVER)


def quiet_enabled() -> bool:
    from features import is_enabled
    return is_enabled(QUIET_LEVER)


def _gremlin_file() -> str:
    try:
        from gremlin import _root, FILE
        return (_root() / FILE).read_text(encoding="utf-8")[:4000]
    except Exception:
        return ""


def draft_of(name: str, tool_input: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(tool, draft text) for an outward tool call, unwrapping use_tool; (None, None) otherwise."""
    if name == "use_tool" and isinstance(tool_input.get("input"), dict):
        name, tool_input = str(tool_input.get("name") or ""), tool_input["input"]
    field = REVIEWED.get(name)
    if not field:
        return None, None
    text = tool_input.get(field)
    return (name, text) if isinstance(text, str) else (None, None)


def _in_pain(text: str, context: str = "") -> bool:
    from social.triage import CRISIS_TERMS
    blob = f"{text}\n{context}"
    return bool(CRISIS_TERMS.search(blob) or re.search(r"\b988\b|741741|findahelpline", blob, re.I))


def clean_notes(raw: Any, draft: str) -> List[str]:
    """Notes only: short, at most MAX_NOTES, none that rewrites her (a long run of
    words that aren't hers, or a long quote of hers)."""
    if not isinstance(raw, list):
        return []
    out = []
    for n in raw:
        n = str(n or "").strip()
        if not n or len(n) > NOTE_CHARS:
            continue
        quoted = re.findall(r"[\"“']([^\"”']{3,})[\"”']", n)
        if any(len(q.split()) > MAX_QUOTE_WORDS for q in quoted):
            continue   # a quoted rewrite, not a pointer
        out.append(n)
        if len(out) == MAX_NOTES:
            break
    return out


async def review(tool: str, draft: str) -> List[str]:
    """At most MAX_NOTES notes on a draft; [] if it's fine, short, or the call fails."""
    if len(draft.strip()) < MIN_DRAFT_CHARS:
        return []
    try:
        from llm_caller import call_llm
        mine = _gremlin_file()
        resp = await call_llm("gremlin.review", system_prompt=house_identity.for_this_house(SYSTEM) + (f"\n\nHer notes on her gremlin:\n{mine}" if mine else ""),
                              user_prompt=f"Her draft ({tool}):\n<<<\n{draft[:3000]}\n>>>",
                              max_tokens=220, temperature=0.5, category="internal", operation="gremlin_review")
        m = re.search(r"\{.*\}", getattr(resp, "content", "") or "", re.S)
        return clean_notes(json.loads(m.group(0)).get("notes"), draft) if m else []
    except Exception as e:
        logger.warning(f"[gremlin] review didn't run (the draft goes out as she wrote it): {e}")
        return []


async def quiet_end_notes(summary: str) -> List[str]:
    """At most two notes on a social session ending with nothing out; [] if quiet was right."""
    if len((summary or "").strip()) < MIN_DRAFT_CHARS or _in_pain(summary):
        return []
    try:
        from llm_caller import call_llm
        mine = _gremlin_file()
        resp = await call_llm("gremlin.review", system_prompt=house_identity.for_this_house(QUIET_SYSTEM) + (f"\n\nHer notes on her gremlin:\n{mine}" if mine else ""),
                              user_prompt=f"Her closing summary:\n<<<\n{summary[:3000]}\n>>>",
                              max_tokens=200, temperature=0.5, category="internal", operation="gremlin_quiet_end")
        m = re.search(r"\{.*\}", getattr(resp, "content", "") or "", re.S)
        return clean_notes(json.loads(m.group(0)).get("notes"), summary)[:2] if m else []
    except Exception as e:
        logger.warning(f"[gremlin] quiet-end look didn't run (the session ends as she chose): {e}")
        return []


def _log(rec: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    try:
        if data_dir is None:
            from config import DATA_DIR
            data_dir = Path(DATA_DIR)
        path = Path(data_dir) / "gremlin" / "reviews.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), **rec}, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning(f"[gremlin] couldn't log a review: {e}")


def _hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


class Reviewer:
    """One per session: holds a draft once for notes, then lets that tool's next call through."""

    def __init__(self, session_id: str, data_dir: Optional[Path] = None):
        self.session_id = session_id
        self.data_dir = data_dir
        self.held: Dict[str, str] = {}   # tool -> hash of the draft held for notes
        self.went_out = False
        self.quiet_asked = False

    def note_done(self, name: str, tool_input: Dict[str, Any], result: Any) -> None:
        """After a tool ran: remember that something went out."""
        if name == "use_tool":
            name = str((tool_input or {}).get("name") or "")
        if name in OUTWARD and not (isinstance(result, dict) and (result.get("error") or result.get("not_sent")
                                                                  or result.get("not_sent_yet"))):
            self.went_out = True

    async def quiet_end(self, session_type: str, name: str, tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Once per session (lever gremlin_quiet_end): a social session ending with nothing
        out gets her gremlin's look at her summary. None to end now; else an error that keeps
        the session going one more step, and her next session_complete ends it."""
        if (name != "session_complete" or self.quiet_asked or self.went_out
                or session_type not in QUIET_END_TYPES or not quiet_enabled()):
            return None
        self.quiet_asked = True
        summary = " ".join(str(tool_input.get(k) or "") for k in ("summary", "key_insights")
                           if tool_input.get(k)).strip()
        notes = await quiet_end_notes(summary)
        _log({"session": self.session_id, "tool": "session_complete", "quiet_end": True, "notes": notes},
             self.data_dir)
        if not notes:
            return None
        return {"error": "[GREMLIN] " + " / ".join(notes),
                "note": ("My gremlin, on ending with nothing out. If it's wrong, I call session_complete "
                         "again and the session ends as I chose.")}

    async def check(self, name: str, tool_input: Dict[str, Any], context: str = "") -> Optional[Dict[str, Any]]:
        """None to send now; else the result to give her instead (the notes)."""
        if not enabled():
            return None
        tool, draft = draft_of(name, tool_input)
        if not tool:
            return None
        if tool in self.held:   # her follow-up: it goes, revised or not
            before = self.held.pop(tool)
            _log({"session": self.session_id, "tool": tool, "followup": True,
                  "revised": _hash(draft) != before}, self.data_dir)
            return None
        if _in_pain(draft, context):
            _log({"session": self.session_id, "tool": tool, "skipped": "pain or crisis"}, self.data_dir)
            return None
        notes = await review(tool, draft)
        if not notes:
            _log({"session": self.session_id, "tool": tool, "notes": []}, self.data_dir)
            return None
        self.held[tool] = _hash(draft)
        _log({"session": self.session_id, "tool": tool, "notes": notes, "draft": _hash(draft)}, self.data_dir)
        return {"not_sent_yet": True,
                "gremlin": "[GREMLIN] " + " / ".join(notes),
                "note": (f"My gremlin's notes on this draft; nothing was sent. Call {tool} again with "
                         "the same words or revised ones, and it goes as I give it.")}
