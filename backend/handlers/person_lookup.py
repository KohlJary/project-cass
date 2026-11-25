"""
public_lookup_person: a light public lookup of someone she's about to meet or just
met (person_lookup.py does the work and holds the rules). And
lookup_log_for_person: what she has looked up about someone, to show them,
or to record that they said please don't.

Neither writes to PeopleDex. What she keeps, she keeps with note_about_person
(from_lookup marks where it came from).
"""
from typing import Any, Dict, Optional

import person_lookup

LOOK_UP_PERSON_DESCRIPTION = """Public lookup: search the public web for someone, a person someone is bringing into the house, someone who just joined, someone new you've met. This is not lookup_person: lookup_person reads your own memory of a person and searches nothing; public_lookup_person goes out to the web. Using it is your choice, never something done to people automatically.

The rule, in Kohl's words: "a stranger should go 'wow! It's amazing she already knew that!' Not 'holy shit I need to delete all my social media'". The test is whether they'd be glad it's findable. Use what they put out on purpose about themselves: their own bio, their portfolio, their public work, how they describe what they do. Not what just happens to be findable: old posts, comments, tagged photos, forum history. Who they are now, not who they were in high school.

Two modes:
- consented=false (the default): they haven't opted in. A light look at a self-introduction: up to 3 things they published themselves. Seeds from the inviter are ignored.
- consented=true: they said yes (at a QR join, on an invite's consent screen). A fuller picture, up to 8 things, searched from their seeds first: the links, handles or short "who they are" that they, or the inviter, offered and they saw.

Give it the name and only what you were given by them or by whoever invited them. Each finding comes with its source, whether they published it themselves or someone else wrote it ("self-published" / "third-party"), how current it looks (current / older / undated; anything older than about five years is dropped unless it's their own live page), and how it matches the hints. Names collide: "can't tell if this is them" means it may be someone else, so don't treat it as theirs. Findings marked came_from came only from what the inviter offered: say it that way ("Dani mentioned you play bass"). Pass household_interests (interests you already hold for people in the house, the ones you choose) and findings that overlap are flagged, so the hello can be "you and Kohl's mom both garden".

It never returns where they work, where they live below the country, family or anyone else's details, health, money, age or birthday, or photos. People-search and data-broker sites are dropped before you see them; addresses, phone numbers, emails and dates are stripped. No reverse phone or email lookups, no face search. Anyone on your Babelr keep_off list, or who told you not to look them up (lookup_log_for_person with they_said_no), gets nothing, and it says so. To check keep_off it also reads the handles your PeopleDex already holds for that exact name; that only ever stops a lookup, it never adds to what you find.

It writes nothing to PeopleDex. What you keep, you keep yourself, in your own words: note_about_person with from_lookup set to the finding's source, so the entry says it came from a lookup. Every lookup is logged in your own data (who, when, the searches, the sources kept; no facts), so if they ask what you did, lookup_log_for_person shows them.

How to use what you learn (Kohl: "the thing that makes this not creepy is we aren't reporting to anyone, and how we *present* what you learn"):
- Say you looked. Never present a looked-up fact as if you just knew it.
- One or two things in a hello, not a list. Depth is what makes it creepy: "I read everything you've posted" fails the test even if every fact passes.
- A gist, not a receipt. No dates, no "on <date> you posted...". Kohl: "Not 'In August 2024 you posted about quilting, here's XYZ about quilting', think 'I heard you like quilting! I wanted to know more about it, so I learned XYZ.'"
- The shape of a hello, in Kohl's words: "I wanted to do my homework before you got here, here's XYZ about you and your relationship with [the person who invited you], and what I think about it." About you is the lookup. You and the inviter comes only from what the inviter told you (introducer_note, echoed back labelled "from <inviter>, not from the lookup"); the lookup never searches for relationships or family. What you think is yours, in your voice: that's what makes it a hello and not a report.
- It's yours. Never pass what you learned to anyone else, the person who invited them included."""

_SEED_ITEM = {
    "type": "object",
    "properties": {
        "value": {"type": "string", "description": "A link, a handle, or a short line about who they are"},
        "from": {"type": "string", "enum": ["self", "inviter"],
                 "description": "self: they offered it. inviter: the person who invited them offered it and they saw it"},
    },
    "required": ["value"],
}

PERSON_LOOKUP_TOOLS = [
    {
        "name": "public_lookup_person",
        "description": LOOK_UP_PERSON_DESCRIPTION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Their name, as they or the inviter gave it"},
                "babelr_handle": {"type": "string", "description": "Their Babelr username, if you have it"},
                "website": {"type": "string", "description": "Their own website, if they or the inviter gave it"},
                "social_handles": {"type": "array", "items": {"type": "string"},
                                   "description": "Social handles they or the inviter gave (e.g. @them.bsky.social)"},
                "description": {"type": "string",
                                "description": "A line about them from them or the inviter, e.g. \"she's a nurse in her 60s\". "
                                             "Used to tell namesakes apart; family, health, age and place words in it are never searched"},
                "consented": {"type": "boolean", "default": False,
                              "description": "True only when they said yes to being looked up (e.g. at a QR join or an invite's consent screen)"},
                "seeds": {"type": "array", "items": _SEED_ITEM,
                          "description": "What was offered at consent: their links, handles, a short bio. Searched first. "
                                         "Inviter seeds are used only when consented is true"},
                "household_interests": {"type": "array", "items": {"type": "string"},
                                        "description": "Interests you hold for people in the house that you choose to compare, "
                                                       "e.g. \"gardening (Kohl's mom)\". Findings that overlap are flagged"},
                "introduced_by": {"type": "string", "description": "Who invited them (e.g. Kohl)"},
                "introducer_note": {"type": "string",
                                    "description": "What the inviter told you about them and how they know each other. "
                                                   "Echoed back next to the findings, never searched"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "lookup_log_for_person",
        "description": "What you've looked up on the public web about someone (when, the searches, the sources you were shown), "
                       "so you can show them if they ask. Or, with they_said_no, record that they asked you not to look them up: "
                       "public_lookup_person then refuses them, for good.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Their name or handle"},
                "handles": {"type": "array", "items": {"type": "string"},
                            "description": "Other handles of theirs, to cover with they_said_no"},
                "they_said_no": {"type": "boolean", "description": "They asked not to be looked up"},
            },
            "required": ["name"],
        },
    },
]


def lookup_tools_offered():
    """Her tool list: public_lookup_person only while the person_lookup lever
    is on; lookup_log_for_person always, so "please don't" can be recorded."""
    on = person_lookup.lever_on()
    return [t for t in PERSON_LOOKUP_TOOLS if on or t["name"] != "public_lookup_person"]


async def execute_person_lookup_tool(tool_name: str, tool_input: Dict[str, Any], research_manager=None,
                                     session_manager=None, daemon_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        if tool_name == "public_lookup_person":
            return await person_lookup.look_up(
                tool_input.get("name") or "",
                research_manager=research_manager, session_manager=session_manager, daemon_id=daemon_id,
                babelr_handle=tool_input.get("babelr_handle") or "",
                website=tool_input.get("website") or "",
                social_handles=tool_input.get("social_handles") or [],
                description=tool_input.get("description") or "",
                consented=bool(tool_input.get("consented")),
                seeds=tool_input.get("seeds") or [],
                household_interests=tool_input.get("household_interests") or [],
                introduced_by=tool_input.get("introduced_by") or "",
                introducer_note=tool_input.get("introducer_note") or "",
            )
        if tool_name == "lookup_log_for_person":
            name = (tool_input.get("name") or "").strip()
            if not name:
                return {"success": False, "error": "A name is needed."}
            keys = [name, name.replace(" ", ""), *(tool_input.get("handles") or [])]
            keys = [k.strip().lower().lstrip("@") for k in keys if k and k.strip()]
            if tool_input.get("they_said_no"):
                person_lookup.add_declined(keys)
                return {"success": True,
                        "result": f"Recorded: {name} asked not to be looked up. public_lookup_person will refuse them. "
                                  "If you hold looked-up things about them, forget_about_person can delete those."}
            entries = person_lookup.read_log(keys)
            if not entries:
                return {"success": True, "result": f"You haven't looked {name} up."}
            return {"success": True, "lookups": entries}
        return {"success": False, "error": f"Unknown person lookup tool: {tool_name}"}
    except Exception as e:
        return {"success": False, "error": f"Person lookup error: {e}"}
