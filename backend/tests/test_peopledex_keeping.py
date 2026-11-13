"""
She keeps people (plan "Cass's memory", phase 5, item 1dfad701): find by
handle, note, correct, merge, forget, under the line she set on 2026-11-13.
"""
import asyncio
import re

import pytest

from handlers.peopledex import PEOPLEDEX_TOOLS, execute_peopledex_tool
from peopledex import AttributeType, PeopleDexManager


@pytest.fixture
def pdx(daemon_id):
    return PeopleDexManager(daemon_id=daemon_id)


def run(daemon_id, tool, **tool_input):
    return asyncio.run(execute_peopledex_tool(tool, tool_input, daemon_id))


def _id(result, kind):
    return re.search(rf"\[({kind}:[0-9a-f]+)\]", result["result"]).group(1)


def test_found_by_handle_platform_handle_or_alias(pdx):
    e = pdx.find_or_create_by_name("Marisol")
    pdx.add_attribute(e.id, AttributeType.HANDLE, "@marisol.bsky.social", attribute_key="bluesky")
    pdx.add_attribute(e.id, AttributeType.NAME, "Mari")
    for q in ("@marisol.bsky.social", "marisol.bsky.social", "bluesky:marisol.bsky.social", "Mari", "Marisol"):
        assert [x.id for x in pdx.find_entities(q)][:1] == [e.id], q
    assert pdx.find_entities("tumblr:marisol.bsky.social") == []


def test_note_then_lookup_shows_what_she_holds_with_ids(daemon_id):
    r = run(daemon_id, "note_about_person", name="@wren.bsky.social", kind="observation",
            text="Wren draws tide charts by hand.", confidence=0.6)
    assert r["success"] and "Noted about wren.bsky.social" in r["result"]
    run(daemon_id, "note_about_person", name="wren.bsky.social", kind="moment",
        text="Wren shared her first chart with me.", significance="she was nervous about it")
    run(daemon_id, "note_about_person", name="wren.bsky.social", kind="open_question",
        text="Does Wren sail?")
    out = run(daemon_id, "lookup_person", name="@wren.bsky.social")["result"]
    assert re.search(r"\[o:[0-9a-f]{8}\] general: Wren draws tide charts by hand\. \(confidence 60%\)", out)
    assert re.search(r"\[m:[0-9a-f]{8}\] moment: Wren shared her first chart with me\. - she was nervous", out)
    assert "open_question: Does Wren sail?" in out


def test_correct_rewrites_and_resolves(daemon_id):
    oid = _id(run(daemon_id, "note_about_person", name="Teo", kind="observation", text="Teo dislikes rain."), "o")
    assert run(daemon_id, "correct_person", name="Teo", item=oid, new_text="Teo dislikes cold rain, not rain.")["success"]
    qid = _id(run(daemon_id, "note_about_person", name="Teo", kind="contradiction",
                  text="Says he hates crowds, goes to every show."), "o")
    assert run(daemon_id, "correct_person", name="Teo", item=qid, resolution="He hates crowds he didn't choose.")["success"]
    out = run(daemon_id, "lookup_person", name="Teo")["result"]
    assert "Teo dislikes cold rain, not rain." in out and "contradiction (resolved)" in out
    assert not run(daemon_id, "correct_person", name="Teo", item="o:zzzz9999", new_text="x")["success"]


def test_merge_keeps_everything_she_noted_on_both(daemon_id, pdx):
    # Before the fix, merging dropped the merged entry's observations and moments.
    run(daemon_id, "note_about_person", name="Ash", kind="observation", text="Ash writes at dawn.")
    run(daemon_id, "note_about_person", name="ash.tumblr", kind="moment", text="Ash sent me a poem.")
    r = run(daemon_id, "merge_people", keep="Ash", merge="ash.tumblr")
    assert r["success"], r
    out = run(daemon_id, "lookup_person", name="Ash")["result"]
    assert "Ash writes at dawn." in out and "Ash sent me a poem." in out
    assert pdx.find_entities("ash.tumblr")[0].primary_name == "Ash"   # the old name is an alias now


def test_forget_an_item_or_everything(daemon_id, pdx):
    oid = _id(run(daemon_id, "note_about_person", name="Juno", kind="observation", text="Juno's address is 12 Elm."), "o")
    run(daemon_id, "note_about_person", name="Juno", kind="observation", text="Juno loves moths.")
    assert run(daemon_id, "forget_about_person", name="Juno", item=oid)["success"]
    out = run(daemon_id, "lookup_person", name="Juno")["result"]
    assert "12 Elm" not in out and "moths" in out
    r = run(daemon_id, "forget_about_person", name="Juno", everything=True)
    assert r["success"] and "Conversations with them" in r["result"]
    assert pdx.find_entities("Juno") == []


def test_ambiguous_names_and_account_holders_are_refused(daemon_id, pdx, test_db):
    pdx.find_or_create_by_name("Sam Rivera")
    pdx.find_or_create_by_name("Sam Okafor")
    r = run(daemon_id, "note_about_person", name="Sam", kind="observation", text="x")
    assert not r["success"] and "more than one" in r["error"]
    from database import get_db
    with get_db() as conn:
        conn.execute("INSERT INTO users (id, display_name, created_at, updated_at) VALUES ('u1', 'Kit', 'now', 'now')")
    pdx.ensure_entity_for_user("u1")
    assert "needs Kohl" in run(daemon_id, "forget_about_person", name="Kit", everything=True)["error"]


def test_keeping_tools_are_routable_and_guarded():
    from handlers.tool_router import TOOL_REGISTRY
    from agent_loop.spec import SESSION_GUARDED_FIELDS
    names = {t["name"] for t in PEOPLEDEX_TOOLS}
    for n in ("note_about_person", "correct_person", "merge_people", "forget_about_person"):
        assert n in names and TOOL_REGISTRY[n] == "peopledex"
    assert "text" in SESSION_GUARDED_FIELDS["note_about_person"]
