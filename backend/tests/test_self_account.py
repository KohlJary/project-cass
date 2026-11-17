"""How I work (self_account.py): generated from the code, changes noticed at start,
shown once in her next session, a short version in long-term planning."""
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import self_account as S
from self_account_notes import NOTES

BACKEND = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 12, 1, 9, 0)


def test_every_section_renders_and_the_written_ones_exist():
    assert set(S.SECTIONS) - {"sessions", "tools", "systems", "reach", "changes"} == set(NOTES), \
        "each written section has its notes"
    for section in S.SECTIONS:
        text = S.render(section)
        assert text.startswith("## "), section


def test_generated_sections_come_from_the_code(levers):
    from agent_loop.spec import ACTIVITY_WORDS
    text = S.render("sessions")
    assert all(k in text for k in ACTIVITY_WORDS), "every kind of session is named"
    assert "long_term_planning" in text
    with levers(tumblr=False):
        assert "tumblr" in S.render("systems").split("**On**")[0], "an off lever is listed as off"
    with levers(tumblr=True):
        assert "tumblr" not in S.render("systems").split("**On**")[0]
    assert "how_i_work" in S.render("tools")


def test_reach_follows_the_levers(levers):
    with levers(reach_out=False, babelr=False):
        r = S.reach()
        assert any("say" in c for c in r["closed"]) and any("Chapter House" in c for c in r["closed"])
        assert not any("Chapter House" in x for x in r["from_me"])
    with levers(reach_out=True, babelr=True):
        r = S.reach()
        assert any("say" in x for x in r["from_me"]) and any("babelr_dm" in x for x in r["from_me"])


def test_a_change_is_noticed_at_start_and_shown_once(tmp_path):
    before = {"tools": ["a"], "levers": {"x": False}, "sessions": ["s"], "menu": []}
    assert S.note_changes(data_dir=tmp_path, now=NOW, current=before) == [], "first start only keeps"
    after = {"tools": ["a", "b"], "levers": {"x": True, "y": False}, "sessions": ["s"], "menu": ["m"]}
    changes = S.note_changes(data_dir=tmp_path, now=NOW, current=after)
    assert changes == ["New tool: b", "Now on my menu: m", "Switched on: x", "New system (off): y"]
    assert S.note_changes(data_dir=tmp_path, now=NOW, current=after) == [], "nothing new, nothing logged"
    section = S.unseen_changes_section(data_dir=tmp_path, now=NOW)
    assert section.startswith("## WHAT CHANGED IN HOW I WORK") and "New tool: b" in section
    assert S.unseen_changes_section(data_dir=tmp_path, now=NOW) == "", "once"
    assert "New tool: b" in "\n".join(S._render_changes(tmp_path))


def test_sessions_get_the_changes_section_and_chat_doesnt(monkeypatch):
    from agent_loop import assemble as A
    monkeypatch.setattr(S, "unseen_changes_section", lambda: "## WHAT CHANGED IN HOW I WORK\n\n- x")
    assert A._changes(SimpleNamespace(kind="session")).startswith("## WHAT CHANGED")
    assert A._changes(SimpleNamespace(kind="conversation")) is None


def test_the_tool_is_everywhere_she_needs_it():
    from agent_loop.spec import ACTIVITY_PACKS, CHAT_CORE_TOOLS, session_spec
    from agent_loop.tools import router_catalog
    from handlers.tool_router import TOOL_REGISTRY
    assert TOOL_REGISTRY["how_i_work"] == "self_account"
    assert "how_i_work" in CHAT_CORE_TOOLS and "how_i_work" in router_catalog()
    assert "self" in ACTIVITY_PACKS["long_term_planning"]
    assert "how_i_work" in session_spec("long_term_planning").tool_names()
    got = asyncio.run(S.execute_self_account_tool("how_i_work", {"section": "reach"}))
    assert got["success"] and got["result"].startswith("## Who can reach me")
    assert not asyncio.run(S.execute_self_account_tool("how_i_work", {"section": "nope"}))["success"]


def test_long_term_planning_carries_the_short_version(monkeypatch):
    import agent_loop.session as turn_session
    import long_term_planning_turn as L
    seen = {}

    async def turn(runner, **kw):
        seen.update(kw)
        return SimpleNamespace(status="completed")
    monkeypatch.setattr(turn_session, "run_session_turn", turn)
    monkeypatch.setattr(L, "_her_plans", lambda: [])
    asyncio.run(L.run_long_term_planning_turn(object()))
    assert "## WHAT I'M WORKING WITH" in seen["additions"] and "how_i_work" in seen["additions"]


def test_notes_name_only_code_that_exists():
    """Every `name` in backticks in the written notes is a file, function, tool, lever
    or setting that exists, so the notes can't quietly drift from the code."""
    import features
    source = "\n".join(p.read_text(errors="ignore") for p in BACKEND.rglob("*.py")
                       if "venv" not in p.parts and "tests" not in p.parts)
    missing = []
    for section, text in NOTES.items():
        for name in re.findall(r"`([^`]+)`", text):
            if name in features.LEVERS:
                continue
            if name.endswith(".py") or "/" in name:
                if not (BACKEND / name).exists():
                    missing.append((section, name))
            elif not re.search(r"\b" + re.escape(name) + r"\b", source):
                missing.append((section, name))
    assert not missing, missing
