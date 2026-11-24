"""People she meets on Babelr, kept in her PeopleDex (spec/house-channel-memory.md, part 3).

Cass, 2026-11-24: Eris filed as a house agent, the guests as people, and anyone
who asks to stay off her PeopleDex is kept off.
"""
import json
from types import SimpleNamespace

from babelr_organ.people import keep_exchange, load_filings
from database import get_daemon_id
from peopledex import EntityType, PeopleDexManager
from social.people import find

FILINGS = {"house": ["eris"], "keep_off": []}
NAMES = {"claude_ai": "Claude", "eris": "Eris", "gemini": "Gemini"}


def ev(author, text, kind="channel"):
    return SimpleNamespace(author_name=author, text=text, kind=kind)


def run(events, reply, dex, filings=FILINGS, links=None, remembers=lambda n: True):
    return keep_exchange(events, reply, place_label="#general", my_username="cass",
                         links=links or {"jaryk": "u-kohl"}, filings=filings,
                         remembers=remembers, display_names=NAMES, dex=dex)


def moments(dex, entity_id):
    return [m.description if hasattr(m, "description") else str(m) for m in dex.get_moments(entity_id)]


def test_a_guest_gets_an_entry_as_a_person_with_the_exchange():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    assert run([ev("claude_ai", "You picked Dre and then wrote Suge's answer.")], "You're right.", dex) == ["claude_ai"]
    eid = find("babelr", "claude_ai", dex)
    e = dex.get_entity(eid)
    assert e.primary_name == "Claude"
    assert e.entity_type in (EntityType.PERSON, "person")
    text = " ".join(moments(dex, eid))
    assert "Babelr in #general" in text and "You're right." in text and "Suge's answer" in text


def test_eris_is_filed_as_house_and_her_existing_entry_is_reused():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    existing = dex.create_entity(EntityType.DAEMON, "Eris")
    run([ev("eris", "Vision doesn't win fights")], "Sister.", dex)
    assert find("babelr", "eris", dex) == existing, "no second Eris"
    assert len([e for e in dex.search_entities("Eris") if e.primary_name == "Eris"]) == 1


def test_eris_without_an_entry_gets_a_daemon_one():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    run([ev("eris", "hi")], "hi", dex)
    e = dex.get_entity(find("babelr", "eris", dex))
    assert e.entity_type in (EntityType.DAEMON, "daemon")


def test_a_guest_is_never_matched_by_name_alone():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    other = dex.create_entity(EntityType.PERSON, "Claude")  # someone else named Claude
    run([ev("claude_ai", "hey")], "hey", dex)
    assert find("babelr", "claude_ai", dex) != other


def test_linked_people_me_and_keep_off_are_left_alone():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    kept = run([ev("jaryk", "crazy day"), ev("cass", "mine"), ev("gemini", "hi")], "ok", dex,
               filings={"house": [], "keep_off": ["gemini"]})
    assert kept == []
    assert find("babelr", "gemini", dex) is None and find("babelr", "jaryk", dex) is None


def test_an_unremembered_dm_isnt_kept():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    assert run([ev("gemini", "secret", kind="dm")], "ok", dex, remembers=lambda n: False) == []


def test_silence_keeps_the_person_but_no_exchange():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    assert run([ev("gemini", "anyone?")], None, dex) == ["gemini"]
    assert moments(dex, find("babelr", "gemini", dex)) == []


def test_a_second_exchange_reuses_the_entry():
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    run([ev("gemini", "one")], "a", dex)
    run([ev("gemini", "two")], "b", dex)
    assert len(moments(dex, find("babelr", "gemini", dex))) == 2


def test_without_a_dex_her_own_daemon_id_is_used():
    # The organ passes no dex and no daemon id; moments must still be kept.
    assert run([ev("gemini", "hello")], "hi", None) == ["gemini"]
    dex = PeopleDexManager(daemon_id=get_daemon_id())
    assert len(moments(dex, find("babelr", "gemini", dex))) == 1


def test_filings_file(tmp_path):
    assert load_filings(tmp_path / "missing.json") == {"house": [], "keep_off": []}
    p = tmp_path / "people.json"
    p.write_text(json.dumps({"house": ["@Eris"], "keep_off": ["gemini"]}))
    assert load_filings(p) == {"house": ["eris"], "keep_off": ["gemini"]}
    p.write_text("{nope")
    assert "*" in load_filings(p)["keep_off"], "an unreadable file keeps nobody new"
