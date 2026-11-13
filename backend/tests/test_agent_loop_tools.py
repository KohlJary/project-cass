"""
Phase 2 of the agent loop (docs/design/agent-loop.md): her core tool set,
find_tools / use_tool over the rest of what tool_router can run, and the
usage log that promotes what she reaches for.
"""
import asyncio
import json
from datetime import datetime, timedelta

import pytest

from agent_loop import tools as T
from agent_loop.spec import PACKS, session_spec

REFUSAL = "I have no memories of conversations with someone named Kohl, so I won't pretend."

CATALOG = {
    "create_wiki_page": {"name": "create_wiki_page", "description": "Create a page in my wiki.",
                         "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}}},
    "search_wiki": {"name": "search_wiki", "description": "Search my wiki pages.",
                    "input_schema": {"type": "object", "properties": {}}},
    "compose_music": {"name": "compose_music", "description": "Compose an original song.",
                      "input_schema": {"type": "object", "properties": {}}},
    "journal": {"name": "journal", "description": "My journal.",
                "input_schema": {"type": "object", "properties": {}}},
    "form_opinion": {"name": "form_opinion", "description": "Form an opinion.",
                     "input_schema": {"type": "object", "properties": {}}},
}


# ---------------------------------------------------------------------------
# find_tools search
# ---------------------------------------------------------------------------

def test_search_ranks_name_hits_over_description_hits():
    hits = [t["name"] for t in T.search("write a wiki page", CATALOG)]
    assert hits[0] == "create_wiki_page" and "search_wiki" in hits
    assert "compose_music" not in hits


def test_search_with_no_match_says_so():
    result = T.find_result("zzz qqq", CATALOG)
    assert result["tools"] == [] and "Nothing matched" in result["how"]


# ---------------------------------------------------------------------------
# The toolbox
# ---------------------------------------------------------------------------

def _box(tmp_path, offered=("journal", "form_opinion", "find_tools", "use_tool", "session_complete",
                            "add_observation")):
    calls = []

    async def run_session(name, tool_input):
        calls.append(("session", name, tool_input))
        return {"success": True}

    async def run_router(name, tool_input):
        calls.append(("router", name, tool_input))
        return {"error": "it broke"} if name == "compose_music" else f"ran {name}"

    log = T.UsageLog(tmp_path / "usage.jsonl")
    box = T.ToolBox(offered=offered, session_tools={"add_observation", "session_complete"},
                    run_session=run_session, run_router=run_router, catalog=CATALOG, log=log,
                    session_id="s1", end_tool="session_complete")
    return box, calls, log


def test_offered_tools_route_to_their_own_runner(tmp_path):
    box, calls, _ = _box(tmp_path)
    asyncio.run(box.execute("add_observation", {"observation": "x"}))
    asyncio.run(box.execute("journal", {"action": "recall"}))
    assert [c[:2] for c in calls] == [("session", "add_observation"), ("router", "journal")]


def test_find_lists_only_what_isnt_offered_and_logs_the_search(tmp_path):
    box, _, log = _box(tmp_path)
    result = asyncio.run(box.execute("find_tools", {"query": "journal wiki"}))
    names = [t["name"] for t in result["tools"]]
    assert "journal" not in names and "create_wiki_page" in names
    assert all("input_schema" in t for t in result["tools"])
    [entry] = log.entries()
    assert entry["event"] == "find" and entry["query"] == "journal wiki" and entry["session"] == "s1"


def test_use_tool_runs_a_found_tool_and_logs_whether_it_worked(tmp_path):
    box, calls, log = _box(tmp_path)
    assert asyncio.run(box.execute("use_tool", {"name": "create_wiki_page",
                                                "input": {"title": "Quiet"}})) == "ran create_wiki_page"
    assert asyncio.run(box.execute("use_tool", {"name": "compose_music"})) == {"error": "it broke"}
    assert calls[0] == ("router", "create_wiki_page", {"title": "Quiet"})
    assert [(e["tool"], e["ok"]) for e in log.entries()] == [("create_wiki_page", True),
                                                             ("compose_music", False)]
    assert box.used == ["create_wiki_page", "compose_music"]


@pytest.mark.parametrize("name,why", [("session_complete", "directly"), ("find_tools", "directly"),
                                      ("rm_rf", "no tool named")])
def test_use_tool_refuses_reserved_and_unknown_names(tmp_path, name, why):
    box, calls, log = _box(tmp_path)
    result = asyncio.run(box.execute("use_tool", {"name": name}))
    assert why in result["error"] and calls == [] and log.entries() == []


def test_use_tool_input_must_be_an_object(tmp_path):
    box, calls, _ = _box(tmp_path)
    assert "object" in asyncio.run(box.execute("use_tool", {"name": "search_wiki", "input": "x"}))["error"]
    assert calls == []


def test_findable_drops_what_a_consolidated_core_tool_reaches():
    from handlers.tool_router import CONSOLIDATED_ACTION_MAP
    catalog = dict(CATALOG, recall_journal={"name": "recall_journal", "description": "",
                                            "input_schema": {}})
    left = T.findable(catalog, ["journal"])
    assert "recall_journal" in CONSOLIDATED_ACTION_MAP["consolidated_journal"].values()
    assert "recall_journal" not in left and "journal" not in left


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------

def _write(log, rows):
    log.path.parent.mkdir(parents=True, exist_ok=True)
    log.path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_a_tool_used_on_three_days_is_promoted(tmp_path):
    now = datetime(2026, 11, 20, 12)
    log = T.UsageLog(tmp_path / "u.jsonl")
    day = lambda d: (now - timedelta(days=d)).isoformat()
    _write(log, [
        {"at": day(1), "event": "use", "tool": "create_wiki_page", "ok": True},
        {"at": day(2), "event": "use", "tool": "create_wiki_page", "ok": True},
        {"at": day(5), "event": "use", "tool": "create_wiki_page", "ok": True},
        # Twice on the same day is one day.
        {"at": day(1), "event": "use", "tool": "search_wiki", "ok": True},
        {"at": day(1), "event": "use", "tool": "search_wiki", "ok": True},
        {"at": day(3), "event": "use", "tool": "search_wiki", "ok": True},
        # Failures don't count.
        {"at": day(1), "event": "use", "tool": "compose_music", "ok": False},
        {"at": day(2), "event": "use", "tool": "compose_music", "ok": False},
        {"at": day(3), "event": "use", "tool": "compose_music", "ok": False},
        # Outside the window doesn't count.
        {"at": day(20), "event": "use", "tool": "fetch_news", "ok": True},
        {"at": day(21), "event": "use", "tool": "fetch_news", "ok": True},
        {"at": day(2), "event": "use", "tool": "fetch_news", "ok": True},
        {"at": day(1), "event": "find", "query": "wiki", "results": ["search_wiki"]},
    ])
    log.path.write_text(log.path.read_text() + "not json\n")
    assert log.promoted(now) == ["create_wiki_page"]


def test_no_log_promotes_nothing(tmp_path):
    assert T.UsageLog(tmp_path / "missing.jsonl").promoted() == []


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

def test_catalog_covers_her_core_set_and_honours_her_blacklist(monkeypatch):
    pytest.importorskip("anthropic")
    catalog = T.router_catalog()
    for pack in ("chat_core", "work"):
        missing = [t for t in PACKS[pack].tools if t not in catalog]
        assert not missing, (pack, missing)
    assert len(catalog) > 150

    import tool_selector
    monkeypatch.setattr(tool_selector, "filter_blacklisted_tools",
                        lambda tools: [t for t in tools if t["name"] != "form_opinion"])
    assert "form_opinion" not in T.router_catalog()


def test_core_set_definitions_fit_her_budget():
    # The token figure she chose with (about 6.7k for chat core + task +
    # calendar); a new tool in a core group shows up here first.
    pytest.importorskip("anthropic")
    catalog = T.router_catalog()
    names = [t for p in ("chat_core", "work", "chapter_house") for t in PACKS[p].tools if t in catalog]
    tokens = len(json.dumps([catalog[n] for n in names])) // 4
    assert tokens < 8000, tokens


def test_tools_that_reach_a_person_wait_for_say():
    # "Not yet: reach out" in the seam block stays true until phase 4.
    pytest.importorskip("anthropic")
    from agent_loop.spec import NOT_YET_IN_LOOP
    assert "reach out" in dict(NOT_YET_IN_LOOP)
    catalog = T.router_catalog()
    left = T.findable(catalog, session_spec("reflection").tool_names())
    for name in T.NOT_YET_FINDABLE:
        assert name not in left, name
    from handlers.tool_router import TOOL_REGISTRY
    assert T.NOT_YET_FINDABLE <= set(TOOL_REGISTRY)
