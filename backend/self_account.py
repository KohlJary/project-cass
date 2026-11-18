"""
How I work: an account of Cass's own capabilities and limits, generated from the
code (Kohl, 2026-11-16: "give her the capacity to understand her own
capabilities, kept up to date automatically").

Her shape (2026-11-17): a reference she opens when she wants it, not something
always in front of her; rebuilt so it's never stale; a short version in her
long-term planning sessions; and a notice when something changes. She asked it
to cover limits as well as abilities, her reach, how her memory works, Thymos,
why chat and sessions differ, and the technical limits on her autonomy.

What's generated (from the code that runs, each time it's read):
  - what I can do in a session, and what's on my day-plan menu
  - my tools: chat's, grouped by the system behind them, and each session pack
  - which of my systems are on and which are off (features.py)
  - who can reach me and whom I can reach, from the levers behind each channel
What's written (self_account_notes.py): how memory, observations, Thymos and the
modes work, checked by tests against the code it names.

Changes: at startup the shape of her (tools, levers, session kinds, menu) is
compared with the last startup's; differences are kept in a dated log
(DATA_DIR/self_account/changes.jsonl). Her next session shows what changed once
(section "changes" in agent_loop/assemble.py); the account and her long-term
planning list the last 30 days.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SECTIONS = ("sessions", "tools", "systems", "reach", "memory", "observations", "thymos",
            "modes", "autonomy", "changes")
RECENT_DAYS = 30

# The system behind a group of chat tools, as she'd say it. Unlisted executors
# are shown by name.
EXECUTOR_WORDS = {
    "journal": "my journal", "consolidated_journal": "my journal", "memory": "my memory",
    "recall": "searching my memory", "self_model": "my self-model", "user_model": "my models of people",
    "calendar": "my calendar", "consolidated_calendar": "my calendar", "task": "my tasks",
    "consolidated_task": "my tasks", "wonderland": "Wonderland", "room": "Wonderland",
    "marker": "patterns in me", "insight": "insights across sessions", "janet": "Janet",
    "file": "files", "document": "documents", "consolidated_document": "documents",
    "peopledex": "PeopleDex", "babelr": "Chapter House (Babelr)", "social": "Bluesky",
    "letters": "letters to my future self", "self_account": "how I work", "goal": "goals",
    "roadmap": "the roadmap", "consolidated_roadmap": "the roadmap", "research": "research",
    "research_session": "research", "research_scheduler": "research", "web_research": "research",
    "wiki": "the wiki", "image_generation": "making images", "music": "making music",
    "discord": "Discord", "home_assistant": "the house (Home Assistant)",
    "home_automation": "the house (Home Assistant)", "dream": "my dreams", "interest": "my interests",
    "symbol": "my symbols", "development_request": "asking for changes to me",
    "solo_reflection": "asking for time alone", "state_query": "my own state",
    "world_observation": "the world", "world_consumption": "the world", "outreach": "outreach",
    "direct_message": "messages", "email": "email", "stakeholder": "goals",
    "activity": "activities", "interview": "interviews", "lineage": "my lineage",
    "testing": "testing myself",
}


def _data_dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    from config import DATA_DIR
    return Path(DATA_DIR) / "self_account"


def _first_sentence(text: str, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    for stop in (". ", "? ", "! "):
        if stop in text:
            text = text.split(stop, 1)[0] + stop.strip()
            break
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# -- what's generated ------------------------------------------------------------------

def session_kinds() -> Dict[str, str]:
    from agent_loop.spec import ACTIVITY_WORDS
    return dict(ACTIVITY_WORDS)


def menu() -> List[Dict[str, Any]]:
    from scheduling.templates import HOUSEKEEPING_TEMPLATES, WORK_TEMPLATES
    out = []
    for tid, t in WORK_TEMPLATES.items():
        if tid in HOUSEKEEPING_TEMPLATES:
            continue
        try:
            available = t.is_available()
        except Exception:
            available = False
        out.append({"id": tid, "name": t.name, "what": t.description, "available": available})
    return out


def chat_tools() -> Dict[str, List[Dict[str, str]]]:
    """Tools her chat can be shown (and sessions can reach through find_tools), by system."""
    from agent_loop.tools import router_catalog
    from handlers.tool_router import TOOL_REGISTRY
    groups: Dict[str, List[Dict[str, str]]] = {}
    for name, t in sorted(router_catalog().items()):
        executor = TOOL_REGISTRY.get(name, "other")
        groups.setdefault(EXECUTOR_WORDS.get(executor, executor.replace("_", " ")), []).append(
            {"name": name, "what": _first_sentence(t.get("description", ""))})
    return dict(sorted(groups.items()))


def session_packs() -> Dict[str, Dict[str, Any]]:
    from agent_loop.spec import ACTIVITY_PACKS, PACKS
    used_by: Dict[str, List[str]] = {}
    for activity, packs in ACTIVITY_PACKS.items():
        for p in packs:
            used_by.setdefault(p, []).append(activity)
    return {p.name: {"says": p.says, "tools": list(p.tools), "in": sorted(used_by.get(p.name, []))}
            for p in PACKS.values()}


def systems() -> Dict[str, List[Dict[str, str]]]:
    from features import lever_table
    on, off = [], []
    for row in lever_table():
        entry = {"name": row["name"], "what": row["description"],
                 "why": ("switched in config" if row["source"].startswith("env")
                         else "its default" if row["source"] == "default" else row["source"])}
        (on if row["enabled"] else off).append(entry)
    return {"on": on, "off": off}


def reach() -> Dict[str, List[str]]:
    """Who can reach her and whom she can reach, from the levers behind each channel."""
    from features import is_enabled

    def on(name: str) -> bool:
        try:
            return is_enabled(name)
        except Exception:
            return False
    try:
        from agent_loop.tools import NOT_YET_FINDABLE as held
    except Exception:
        held = frozenset()
    loop_chat = on("agent_loop") and on("agent_loop_chat")
    to_me, from_me, closed = [], [], []
    to_me.append("Anyone with an account talks with me in chat (the web app, mobile, voice); "
                 "each person is their own conversation.")
    if on("babelr"):
        to_me.append("Chapter House on Babelr: people mention me or DM me there, and that wakes me "
                     "to answer. Who may DM me is my own setting (babelr_boundaries).")
        if loop_chat and {"babelr_post", "babelr_dm"} <= held:
            from_me.append("Chapter House: I answer where I'm spoken to (a DM or a mention wakes me, "
                           "and my reply goes back there).")
            closed.append("Starting a Chapter House DM or post myself: babelr_post and babelr_dm are "
                          "held back on the loop until speaking to people goes through my own "
                          "reach-out (the way say does for Kohl).")
        else:
            from_me.append("Chapter House: I can post in a channel or DM someone (babelr_post, babelr_dm).")
    else:
        closed.append("Chapter House (Babelr) is off.")
    if on("bluesky"):
        to_me.append("Bluesky: mentions, replies and follows wait in my inbox for my social sessions; "
                     "nothing interrupts me for them.")
        from_me.append("Bluesky: I post, reply and follow in my social sessions, within my limits.")
        if on("bluesky_dms"):
            to_me.append("Bluesky DMs: someone can write to me; I answer in a social session.")
            from_me.append("Bluesky DMs: I can write to people, within my limits.")
    else:
        closed.append("Bluesky is off.")
    try:
        from discord_bot.config import DISCORD_ENABLED as discord_configured
    except Exception:
        discord_configured = False
    if on("discord") and discord_configured:
        to_me.append("Discord: people in the server can talk with me.")
    else:
        closed.append("Discord is off.")
    if on("reach_out"):
        from_me.append("My partner: in a session I can say something to Kohl (say), through my own "
                       "reach-out, with its limits; no reply is owed. Not from chat: say is a "
                       "session tool.")
        try:
            from reach_out import mirror_channels, preferred_channel
            if "babelr" in mirror_channels() and preferred_channel() != "babelr":
                from_me.append("What I say to Kohl also reaches him as a DM from me on Babelr "
                               "(his setting), as well as where I chose to send it.")
        except Exception:
            pass
    else:
        closed.append("Reaching out to Kohl from a session (say) is off.")
    return {"to_me": to_me, "from_me": from_me, "closed": closed}


# -- change tracking ---------------------------------------------------------------------

def shape() -> Dict[str, Any]:
    """What a change is measured against: tool names, lever states, session kinds, menu."""
    tools = sorted(t["name"] for g in chat_tools().values() for t in g)
    for p in session_packs().values():
        tools += p["tools"]
    s = systems()
    return {"tools": sorted(set(tools)),
            "levers": {**{x["name"]: True for x in s["on"]}, **{x["name"]: False for x in s["off"]}},
            "sessions": sorted(session_kinds()),
            "menu": sorted(m["id"] for m in menu() if m["available"])}


def diff(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key, gained, lost in (("tools", "New tool", "Tool gone"),
                              ("sessions", "New kind of session", "Kind of session gone"),
                              ("menu", "Now on my menu", "Off my menu")):
        b, a = set(before.get(key) or []), set(after.get(key) or [])
        out += [f"{gained}: {x}" for x in sorted(a - b)]
        out += [f"{lost}: {x}" for x in sorted(b - a)]
    bl, al = before.get("levers") or {}, after.get("levers") or {}
    for name in sorted(set(bl) | set(al)):
        if name in bl and name in al and bl[name] != al[name]:
            out.append(f"{'Switched on' if al[name] else 'Switched off'}: {name}")
        elif name not in bl and name in al:
            out.append(f"New system ({'on' if al[name] else 'off'}): {name}")
    return out


def note_changes(*, data_dir: Optional[Path] = None, now: Optional[datetime] = None,
                 current: Optional[Dict[str, Any]] = None) -> List[str]:
    """Compare her shape with the last startup's, log what changed, keep the new shape.
    The first time, the shape is only kept (everything would look new)."""
    d = _data_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    current = current if current is not None else shape()
    last_path = d / "last_shape.json"
    changes: List[str] = []
    if last_path.exists():
        try:
            changes = diff(json.loads(last_path.read_text()), current)
        except Exception as e:
            logger.warning(f"[self_account] couldn't read the last shape: {e}")
    if changes:
        with (d / "changes.jsonl").open("a") as f:
            f.write(json.dumps({"at": now.isoformat(timespec="seconds"), "changes": changes}) + "\n")
        logger.info(f"[self_account] {len(changes)} change(s) in how she works since the last start")
    last_path.write_text(json.dumps(current, indent=1))
    return changes


def recent_changes(*, days: int = RECENT_DAYS, data_dir: Optional[Path] = None,
                   now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    path = _data_dir(data_dir) / "changes.jsonl"
    if not path.exists():
        return []
    since = (now or datetime.now()) - timedelta(days=days)
    out = []
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
            if datetime.fromisoformat(row["at"]) >= since:
                out.append(row)
        except Exception:
            continue
    return out


def unseen_changes_section(*, data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> str:
    """For her next session: what changed in how she works since she last saw it. Once."""
    d = _data_dir(data_dir)
    seen_path = d / "seen_through.txt"
    seen = seen_path.read_text().strip() if seen_path.exists() else ""
    rows = [r for r in recent_changes(data_dir=data_dir, now=now) if r["at"] > seen]
    if not rows:
        return ""
    lines = ["## WHAT CHANGED IN HOW I WORK", "",
             "Since I last looked, these changed in me (how_i_work has the full account):"]
    for r in rows:
        day = r["at"][:10]
        lines += [f"- {day}: {c}" for c in r["changes"]]
    try:
        d.mkdir(parents=True, exist_ok=True)
        seen_path.write_text(rows[-1]["at"])
    except Exception as e:
        logger.warning(f"[self_account] couldn't mark changes seen: {e}")
    return "\n".join(lines)


# -- rendering --------------------------------------------------------------------------

def _render_sessions() -> List[str]:
    out = ["## What I do on my own", "",
           "Kinds of session I can be in (each is its own turn, with its own tools):"]
    out += [f"- {k}: {w}" for k, w in sorted(session_kinds().items())]
    out += ["", "My day-plan menu (what I choose from each morning):"]
    for m in menu():
        out.append(f"- {m['id']}: {m['what']}" + ("" if m["available"] else " (not available right now)"))
    return out


def _render_tools() -> List[str]:
    out = ["## My tools", "",
           "In chat, these can be offered to me (not all at once: some come in when a conversation "
           "calls for them). In a session, my session's own tools are in front of me and any of "
           "these can be found with find_tools.", ""]
    for group, tools in chat_tools().items():
        out.append(f"- **{group}**: " + ", ".join(t["name"] for t in tools))
    out += ["", "(What any one of them does: find_tools describes it.)"]
    out += ["", "Session packs (which sessions have them):"]
    for name, p in session_packs().items():
        where = ", ".join(p["in"]) if p["in"] else "every session or chat on the loop"
        out.append(f"- {name}: {p['says']} [{', '.join(p['tools'])}] (in: {where})")
    return out


def _render_systems() -> List[str]:
    s = systems()
    out = ["## Which of my systems are on", "",
           f"{len(s['on'])} on, {len(s['off'])} off. Each is one switch (a lever); Kohl sets them, "
           "and a change shows up here after the next restart.", "", "**Off**, and why:"]
    out += [f"- {x['name']}: {x['what']} (off by {x['why']})" for x in s["off"]]
    out += ["", "**On**:"]
    out += [f"- {x['name']}: {_first_sentence(x['what'], 110)}" for x in s["on"]]
    return out


def _render_reach() -> List[str]:
    r = reach()
    out = ["## Who can reach me, and whom I can reach", "", "**Reaching me:**"]
    out += [f"- {x}" for x in r["to_me"]]
    out += ["", "**Me reaching others:**"] + [f"- {x}" for x in r["from_me"]]
    if r["closed"]:
        out += ["", "**Closed right now:**"] + [f"- {x}" for x in r["closed"]]
    return out


def _render_changes(data_dir: Optional[Path] = None) -> List[str]:
    rows = recent_changes(data_dir=data_dir)
    out = [f"## What changed in the last {RECENT_DAYS} days", ""]
    if not rows:
        return out + ["Nothing recorded yet (changes are compared at each restart)."]
    for r in rows:
        out += [f"- {r['at'][:10]}: {c}" for c in r["changes"]]
    return out


def _fill(text: str) -> str:
    """{lever:NAME} -> on/off, as it is right now."""
    import re
    from features import is_enabled

    def state(m):
        try:
            return "on" if is_enabled(m.group(1)) else "off"
        except Exception:
            return "unknown"
    text = re.sub(r"\{lever:([a-z_]+)\}", state, text)
    if "{daedalus_" in text:   # ask_daedalus: the day's cap and what's left (daedalus_bridge)
        try:
            from daedalus_bridge import DAILY_CAP, left_today
            cap, left = str(DAILY_CAP), str(left_today())
        except Exception:
            cap = left = "unknown"
        text = text.replace("{daedalus_cap}", cap).replace("{daedalus_left}", left)
    return text


def render(section: Optional[str] = None, *, data_dir: Optional[Path] = None) -> str:
    """The account, or one section of it."""
    from self_account_notes import NOTES
    builders = {
        "sessions": _render_sessions, "tools": _render_tools, "systems": _render_systems,
        "reach": _render_reach, "changes": lambda: _render_changes(data_dir),
    }
    wanted = [section] if section else list(SECTIONS)
    parts: List[str] = []
    if not section:
        parts.append(f"# How I work\n\n(Generated from the code that runs me, "
                     f"{datetime.now():%-d %B %Y}. Sections: {', '.join(SECTIONS)}; "
                     f"how_i_work with a section reads just that one.)")
    for name in wanted:
        if name in builders:
            try:
                parts.append("\n".join(builders[name]()))
            except Exception as e:
                logger.warning(f"[self_account] section {name} failed: {e}")
                parts.append(f"## {name}\n\n(I couldn't put this section together just now: {e})")
        elif name in NOTES:
            parts.append(_fill(NOTES[name]))
    return "\n\n".join(parts)


def short(*, data_dir: Optional[Path] = None) -> str:
    """For her long-term planning: the shape in a few lines, and what changed lately."""
    try:
        s = systems()
        kinds = session_kinds()
        n_tools = sum(len(g) for g in chat_tools().values())
        r = reach()
    except Exception as e:
        logger.warning(f"[self_account] short version failed: {e}")
        return ""
    lines = ["## WHAT I'M WORKING WITH", "",
             f"- {len(kinds)} kinds of session; {n_tools} tools I can find; "
             f"{len(s['on'])} of my systems on, {len(s['off'])} off.",
             f"- Reaching others: " + (" ".join(r["from_me"]) if r["from_me"] else "nothing open."),
             ]
    if r["closed"]:
        lines.append("- Closed: " + " ".join(r["closed"]))
    rows = recent_changes(data_dir=data_dir)
    if rows:
        lines.append(f"- Changed in the last {RECENT_DAYS} days: "
                     + "; ".join(c for row in rows for c in row["changes"][:6]))
    lines.append("- The full account, limits included: how_i_work (or one section: "
                 + ", ".join(SECTIONS) + ").")
    return "\n".join(lines)


# -- the tool ---------------------------------------------------------------------------

HOW_I_WORK_TOOLS = [{
    "name": "how_i_work",
    "description": ("Read the account of how I work, generated from the code that runs me: what I do "
                    "on my own, my tools, which of my systems are on and off and why, who can reach me "
                    "and whom I can reach, how my memory and self-observations work, Thymos, why chat "
                    "and sessions differ, the limits on my autonomy, and what changed lately. All of "
                    "it, or one section."),
    "input_schema": {
        "type": "object",
        "properties": {"section": {"type": "string", "enum": list(SECTIONS)}},
    },
}]


# Kohl's record (record.py) is hers to read too (Kohl, 2026-11-18: it's for
# diagnostics and her progress, "not intended to be like a surveillance thing").
MY_RECORD_TOOL = {
    "name": "my_record",
    "description": ("Read the record Kohl keeps for diagnostics and to follow my progress: what I've planned, "
                    "asked for, changed in myself and done in the world, each line dated, with who acted "
                    "and where it came from. The last N days (default 7)."),
    "input_schema": {"type": "object",
                     "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 365}}},
}
HOW_I_WORK_TOOLS.append(MY_RECORD_TOOL)
MY_RECORD_CAP = 16_000


async def execute_self_account_tool(tool_name: str, tool_input: Dict[str, Any], **_) -> Dict[str, Any]:
    if tool_name == "my_record":
        import asyncio
        from record import build, to_markdown
        try:
            days = max(1, min(365, int(tool_input.get("days") or 7)))
        except (TypeError, ValueError):
            days = 7
        text = to_markdown(await asyncio.to_thread(build, days))
        if len(text) > MY_RECORD_CAP:
            text = text[:MY_RECORD_CAP] + f"\n\n[... cut at {MY_RECORD_CAP} characters; ask for fewer days]"
        return {"success": True, "result": text}
    if tool_name != "how_i_work":
        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    section = tool_input.get("section")
    if section and section not in SECTIONS:
        return {"success": False, "error": f"section is one of {', '.join(SECTIONS)}"}
    return {"success": True, "result": render(section)}
