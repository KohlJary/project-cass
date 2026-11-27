"""
public_lookup_person (person_lookup.py, handlers/person_lookup.py): a light public
lookup, guarded in code. The web is a fake here; nothing leaves the machine.
"""
import asyncio
import json
from datetime import datetime, timezone

import pytest

import person_lookup as pl
from handlers.person_lookup import PERSON_LOOKUP_TOOLS, execute_person_lookup_tool

THIS_YEAR = datetime.now(timezone.utc).year


class FakeWeb:
    """research_manager stand-in: canned results, every call recorded."""

    def __init__(self, results=None, pages=None):
        self.results = results or []
        self.pages = pages or {}
        self.searches = []
        self.fetches = []

    async def web_search(self, query, num_results=10, search_depth="basic", include_domains=None,
                         exclude_domains=None):
        self.searches.append({"query": query, "include": include_domains, "exclude": exclude_domains})
        return {"success": True, "answer": "Wren lives at 12 Elm Street and works at Acme.",
                "results": [dict(r) for r in self.results]}

    async def fetch_url(self, url, extract_mode="article"):
        self.fetches.append(url)
        page = self.pages.get(url)
        if page is None:
            return {"success": False, "error": "HTTP 404", "content": ""}
        return {"success": True, "title": page[0], "content": page[1]}


@pytest.fixture(autouse=True)
def lever_on(levers):
    # The test profile turns every lever off; these tests are about the tool working.
    with levers(person_lookup=True):
        yield


@pytest.fixture(autouse=True)
def lookup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "DATA_DIR_OVERRIDE", tmp_path / "person_lookup")
    monkeypatch.setattr(pl, "babelr_keep_off", lambda: [])
    return tmp_path / "person_lookup"


def look(web, name="Wren Alder", **kw):
    return asyncio.run(pl.look_up(name, research_manager=web, **kw))


def hit(url, snippet, title="Wren Alder"):
    return {"url": url, "title": title, "snippet": snippet}


def facts(out):
    return [f["fact"] for f in out["findings"]]


# --- sites that never reach her -------------------------------------------

def test_blocklisted_domains_are_dropped_and_excluded_from_the_search():
    web = FakeWeb([
        hit("https://www.spokeo.com/Wren-Alder", "Wren Alder is a potter who loves birds."),
        hit("https://people.whitepages.com/wren", "Wren Alder is a potter who loves birds."),
        hit("https://radaris.com/p/Wren/Alder/", "Wren Alder is a potter who loves birds."),
        hit("https://www.linkedin.com/in/wren", "Wren Alder is a potter who loves birds."),
        hit("https://fine.example.org/a", "Wren Alder is a potter who loves birds."),
    ])
    out = look(web, consented=True)
    assert [f["source"] for f in out["findings"]] == ["https://fine.example.org/a"]
    assert out["left_out"]["blocked_sites"] == 4
    assert all("spokeo.com" in s["exclude"] and "truepeoplesearch.com" in s["exclude"] for s in web.searches)
    for d in ("spokeo.com", "whitepages.com", "beenverified.com", "truepeoplesearch.com", "fastpeoplesearch.com",
              "radaris.com", "mylife.com", "intelius.com", "peoplefinders.com"):
        assert pl.is_blocked(f"https://www.{d}/x") and pl.is_blocked(f"https://sub.{d}/x")
    assert not pl.is_blocked("https://notspokeo.com/x")


def test_a_search_engines_summary_answer_never_reaches_her():
    out = look(FakeWeb([hit("https://fine.example.org/a", "Wren Alder is a potter.")]), consented=True)
    assert "Acme" not in json.dumps(out) and "Elm" not in json.dumps(out)


def test_single_posts_comments_and_photos_are_dropped():
    web = FakeWeb([
        hit("https://twitter.com/wren/status/12345", "Wren Alder loves quilting."),
        hit("https://bsky.app/profile/wren.bsky.social/post/3kabc", "Wren Alder loves quilting."),
        hit("https://www.reddit.com/r/quilting/comments/abc/x/", "Wren Alder loves quilting."),
        hit("https://forum.example.com/t/quilts/991", "Wren Alder loves quilting."),
        hit("https://example.com/photos/wren.jpg", "Wren Alder loves quilting."),
    ])
    out = look(web, consented=True)
    assert out["findings"] == []
    assert out["left_out"]["single_posts_or_comments"] == 4 and out["left_out"]["photos"] == 1


# --- what's stripped and what's dropped -----------------------------------

def test_addresses_and_phone_numbers_are_stripped():
    text = ("I make quilts to order: call (503) 555-0142 or +44 20 7946 0958, write to wren@example.com, "
            "or visit 1234 N Main Street, Apt 5, Portland, OR 97201. P.O. Box 77.")
    cleaned = pl.strip_private(text)
    for gone in ("555-0142", "7946", "wren@example.com", "1234", "Main Street", "97201", "Box 77"):
        assert gone not in cleaned, gone
    assert "I make quilts to order" in cleaned

    page = "I make quilts to order, ring 503-555-0142 any time. My studio is at 88 Mill Road."
    web = FakeWeb(pages={"https://wrenalder.com": ("Wren Alder", page)})
    out = look(web, website="wrenalder.com")
    blob = json.dumps(out["findings"])
    assert "quilts" in blob and "555" not in blob and "Mill Road" not in blob


def test_workplace_dropped_occupation_kept():
    web = FakeWeb([
        hit("https://a.example.org/1", "Wren Alder works at Acme Widgets Inc as a lead."),
        hit("https://b.example.org/2", "Wren Alder is a nurse at St Mary's Hospital."),
        hit("https://c.example.org/3", "Wren Alder is employed by Initech."),
    ])
    out = look(web, consented=True)
    assert facts(out) == ["Wren Alder is a nurse."]
    blob = json.dumps(out)
    assert "Acme" not in blob and "Mary" not in blob and "Initech" not in blob


@pytest.mark.parametrize("sentence", [
    "Wren Alder lives in Portland and loves birds.",
    "Wren Alder, a potter, is married with two kids.",
    "Wren Alder is a potter who was diagnosed with cancer.",
    "Wren Alder is a potter with a net worth of $2 million.",
    "Wren Alder is a 62-year-old potter.",
    "Wren Alder is a potter, born in 1962.",
    "Wren Alder posted about pottery.",
])
def test_off_limits_kinds_never_reach_her(sentence):
    out = look(FakeWeb([hit("https://a.example.org/1", sentence)]), consented=True)
    assert out["findings"] == [], sentence


def test_a_country_is_fine():
    out = look(FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter based in Canada.")]), consented=True)
    assert facts(out) == ["Wren Alder is a potter based in Canada."]


def test_hint_words_are_never_family_health_or_places():
    assert pl.hint_terms("she's a nurse in her 60s, Kohl's cousin from Portland, recovering from surgery",
                         exclude=["Kohl"]) == ["nurse"]


# --- who isn't looked up ----------------------------------------------------

def test_keep_off_returns_nothing_and_searches_nothing(monkeypatch):
    monkeypatch.setattr(pl, "babelr_keep_off", lambda: ["wren"])
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter.")])
    out = look(web, babelr_handle="@Wren", consented=True)
    assert out["findings"] == [] and "keep_off" in out["declined"]
    assert web.searches == [] and web.fetches == []


def test_an_unreadable_keep_off_list_looks_up_nobody(monkeypatch):
    monkeypatch.setattr(pl, "babelr_keep_off", lambda: ["*"])
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter.")])
    out = look(web)
    assert out["findings"] == [] and web.searches == []


def test_please_dont_is_final():
    r = asyncio.run(execute_person_lookup_tool("lookup_log_for_person",
                                               {"name": "Wren Alder", "they_said_no": True}))
    assert r["success"]
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter.")])
    out = look(web, consented=True)
    assert out["findings"] == [] and "said please don't" in out["declined"] and web.searches == []


# --- it writes nothing ------------------------------------------------------

def test_it_never_writes_to_peopledex(daemon_id, monkeypatch):
    import peopledex

    def refuse(*a, **k):
        raise AssertionError("public_lookup_person wrote to PeopleDex")

    for m in ("create_entity", "find_or_create_by_name", "add_attribute", "add_observation", "add_moment",
              "add_relationship", "add_fact", "update_entity", "update_attribute", "delete_entity"):
        monkeypatch.setattr(peopledex.PeopleDexManager, m, refuse)
    before = len(peopledex.PeopleDexManager(daemon_id=daemon_id).list_entities())

    from handlers.tool_router import ToolContext, route_tool

    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter who loves birds.")],
                  pages={"https://wrenalder.com": ("Wren", "I make pots.")})
    ctx = ToolContext(daemon_id=daemon_id, research_manager=web)
    r = asyncio.run(route_tool("public_lookup_person", {"name": "Wren Alder", "website": "wrenalder.com",
                                                  "consented": True},
                               ctx, {"person_lookup": execute_person_lookup_tool}))
    assert r["success"] and r["findings"]
    assert len(peopledex.PeopleDexManager(daemon_id=daemon_id).list_entities()) == before


# --- matching ---------------------------------------------------------------

def test_results_that_dont_match_the_hints_are_labelled():
    web = FakeWeb([
        hit("https://a.example.org/1", "Wren Alder is a nurse who loves quilting."),
        hit("https://b.example.org/2", "Wren Alder is a software engineer."),
        hit("https://c.example.org/3", "Someone else entirely is a potter.", "Potters"),
    ])
    out = look(web, description="she's a nurse in her 60s", consented=True)
    by = {f["source"]: f["match"] for f in out["findings"]}
    assert by["https://a.example.org/1"].startswith("matches your hints (nurse)")
    assert by["https://b.example.org/2"] == "can't tell if this is them"
    assert "https://c.example.org/3" not in by and out["left_out"]["not_about_them"] == 1
    assert out["findings"][0]["source"] == "https://a.example.org/1"


def test_their_own_site_is_self_published_and_first():
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter.")],
                  pages={"https://wrenalder.com": ("Wren", "Hi, I'm Wren. I throw pots and teach workshops.")})
    out = look(web, website="wrenalder.com", consented=True)
    first = out["findings"][0]
    assert first["source"] == "https://wrenalder.com" and first["source_kind"] == "self-published"
    assert first["match"].startswith("this is them")
    assert out["findings"][1]["source_kind"] == "third-party"


def test_a_handle_on_a_shared_host_only_claims_their_own_path():
    h = pl.Hints("Wren Alder")
    h.give("https://instagram.com/wrenmakes", "a link they offered you", "self")
    assert h.source_kind("https://instagram.com/wrenmakes/")[0] == "self-published"
    assert h.source_kind("https://instagram.com/someoneelse")[0] == "third-party"


# --- recency ----------------------------------------------------------------

def test_newer_ranks_above_older_and_stale_is_dropped():
    web = FakeWeb([
        hit(f"https://a.example.org/{THIS_YEAR - 4}/05/show", "Wren Alder exhibited her quilts."),
        hit(f"https://b.example.org/{THIS_YEAR}/01/show", "Wren Alder exhibited her ceramics."),
        hit(f"https://c.example.org/{THIS_YEAR - 12}/05/hs", "Wren Alder won the school art prize."),
        hit("https://d.example.org/x", "Wren Alder makes zines."),
    ])
    out = look(web, consented=True)
    order = [(f["source"].split("/")[2], f["how_current"]) for f in out["findings"]]
    assert order == [("b.example.org", "current"), ("d.example.org", "undated"), ("a.example.org", "older")]
    assert out["left_out"]["older_than_five_years"] == 1
    assert not any(str(THIS_YEAR) in f["fact"] for f in out["findings"]), "no dates in what she reads"


def test_their_own_live_page_stays_current_even_with_an_old_year():
    page = f"I've made ceramics since {THIS_YEAR - 20}. I teach wheel classes."
    out = look(FakeWeb(pages={"https://wrenalder.com": ("Wren", page)}), website="wrenalder.com")
    assert out["findings"][0]["how_current"].startswith("current")
    assert str(THIS_YEAR - 20) not in out["findings"][0]["fact"]


# --- consent: caps, seeds, inviter seeds -------------------------------------

def _many(n):
    return [hit(f"https://site{i}.example.org/a", f"Wren Alder makes zines number {i}.") for i in range(n)]


def test_consented_gets_up_to_eight_unconsented_three_and_only_self_published():
    out = look(FakeWeb(_many(12)), consented=True)
    assert len(out["findings"]) == pl.MAX_FACTS_CONSENTED == 8

    light = look(FakeWeb(_many(12)), consented=False)
    assert light["findings"] == [] and light["left_out"]["third_party_without_consent"] == 12

    own = [hit(f"https://wrenmakes.site{i}.com/", "I make zines and loves birds.") for i in range(6)]
    light = look(FakeWeb(own + _many(4)), social_handles=["@wrenmakes"])
    assert len(light["findings"]) == pl.MAX_FACTS_LIGHT == 3
    assert {f["source_kind"] for f in light["findings"]} == {"self-published"}


def test_seeds_are_read_first_and_phone_or_email_seeds_are_never_looked_up():
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter.")],
                  pages={"https://wren.studio/about": ("About", "I'm Wren. I weave rugs.")})
    out = look(web, consented=True, seeds=[{"value": "https://wren.studio/about", "from": "self"},
                                           {"value": "@wrenweaves", "from": "self"},
                                           {"value": "+1 503 555 0142", "from": "self"},
                                           {"value": "wren@example.com", "from": "self"},
                                           {"value": "I weave rugs and keep bees", "from": "self"}])
    assert web.fetches[0] == "https://wren.studio/about"
    assert web.searches[0]["query"] == '"wrenweaves"'
    assert not any("555" in s["query"] or "example.com" in s["query"] for s in web.searches)
    assert out["left_out"]["seeds_not_used"] == 2
    assert out["findings"][0]["match"] == "this is them: their own words"
    assert out["findings"][0]["source_kind"] == "self-published"


def test_inviter_seeds_are_ignored_without_consent_and_labelled_with_it():
    seeds = [{"value": "Wren plays bass in a folk band", "from": "inviter"},
             {"value": "@wren.bsky.social", "from": "inviter"}]
    web = FakeWeb([hit("https://bsky.app/profile/wren.bsky.social", "bass player, folk songs", "Wren")])
    light = look(web, seeds=seeds, introduced_by="Dani")
    assert light["findings"] == [] and light["left_out"]["inviter_seeds_ignored_without_consent"] == 2
    assert all("wren.bsky.social" not in s["query"] for s in web.searches)

    full = look(FakeWeb(web.results), seeds=seeds, introduced_by="Dani", consented=True)
    by = {f["fact"]: f for f in full["findings"]}
    bio = by["Wren plays bass in a folk band."]
    assert bio["source_kind"] == "from Dani" and "Dani mentioned" in bio["came_from"]
    profile = by["bass player, folk songs."]
    assert profile["source_kind"] == "self-published" and "Dani" in profile["came_from"]


def test_the_inviters_note_is_echoed_and_labelled_never_searched():
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter.")])
    out = look(web, introduced_by="Kohl", introducer_note="My old friend from nursing school, Lena's aunt")
    assert out["from_the_inviter"] == {"from": "Kohl", "note": "My old friend from nursing school, Lena's aunt",
                                       "label": "from Kohl, not from the lookup"}
    assert not any("nursing" in s["query"] or "Lena" in s["query"] for s in web.searches)


# --- shared interests ---------------------------------------------------------

def test_overlap_with_household_interests_is_flagged():
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder loves gardening and birdwatching."),
                   hit("https://b.example.org/2", "Wren Alder makes zines.")])
    out = look(web, consented=True, household_interests=["gardening (Kohl's mom)", "chess"])
    by = {f["source"]: f for f in out["findings"]}
    assert by["https://a.example.org/1"]["shared_interests"] == ["gardening (Kohl's mom)"]
    assert "shared_interests" not in by["https://b.example.org/2"]


# --- the log ------------------------------------------------------------------

def test_every_lookup_is_logged_with_counts_and_urls_only(lookup_dir, monkeypatch):
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter who loves birds."),
                   hit("https://spokeo.com/w", "Wren Alder")])
    look(web, consented=True, babelr_handle="wren")
    monkeypatch.setattr(pl, "babelr_keep_off", lambda: ["wren"])
    look(web, babelr_handle="wren")
    lines = [json.loads(x) for x in (lookup_dir / "lookups.jsonl").read_text().splitlines()]
    assert [e["outcome"] for e in lines] == ["ok", "declined"]
    e = lines[0]
    assert set(e) == {"at", "who", "consented", "handles", "hints_given", "queries", "fetched",
                      "sources_kept", "left_out", "outcome"}
    assert e["who"] == "Wren Alder" and e["sources_kept"] == ["https://a.example.org/1"]
    assert e["left_out"] == {"blocked_sites": 1}
    assert "potter" not in json.dumps(lines), "no facts in the log"
    shown = asyncio.run(execute_person_lookup_tool("lookup_log_for_person", {"name": "wren"}))
    assert len(shown["lookups"]) == 2


# --- filing, and where she sees it ---------------------------------------------

def test_from_lookup_marks_an_observation(daemon_id):
    from handlers.peopledex import execute_peopledex_tool
    r = asyncio.run(execute_peopledex_tool("note_about_person", {
        "name": "Wren Alder", "kind": "observation", "text": "Wren throws pots.",
        "from_lookup": "https://wrenalder.com"}, daemon_id))
    assert r["success"]
    out = asyncio.run(execute_peopledex_tool("lookup_person", {"name": "Wren Alder"}, daemon_id))["result"]
    assert "Wren throws pots. (source: public lookup, https://wrenalder.com)" in out


def test_registered_on_her_tool_list():
    from handlers.tool_router import TOOL_REGISTRY
    assert TOOL_REGISTRY["public_lookup_person"] == TOOL_REGISTRY["lookup_log_for_person"] == "person_lookup"
    from agent_loop.tools import router_catalog
    assert {"public_lookup_person", "lookup_log_for_person"} <= set(router_catalog())
    desc = next(t for t in PERSON_LOOKUP_TOOLS if t["name"] == "public_lookup_person")["description"]
    assert "amazing she already knew that" in desc and "Say you looked" in desc
    assert pl.wants_lookup_tools("Kohl's bringing two people over this weekend, want to meet them?")
    assert pl.wants_lookup_tools("remember that Ash goes by they")
    assert not pl.wants_lookup_tools("what's the weather")



def test_main_sdk_runs_it():
    # main_sdk needs the server's runtime deps, which CI's fast job doesn't install.
    pytest.importorskip("slowapi")
    import main_sdk
    assert "person_lookup" in main_sdk.TOOL_EXECUTORS

def test_the_lever_is_a_kill_switch(levers):
    from agent_loop.tools import router_catalog
    from handlers.person_lookup import lookup_tools_offered
    web = FakeWeb([hit("https://a.example.org/1", "Wren Alder is a potter.")])
    with levers(person_lookup=False):
        out = look(web)
        assert not out["success"] and "switched off" in out["error"] and web.searches == []
        assert [t["name"] for t in lookup_tools_offered()] == ["lookup_log_for_person"]
        catalog = router_catalog()
        assert "public_lookup_person" not in catalog and "lookup_log_for_person" in catalog
        r = asyncio.run(execute_person_lookup_tool("lookup_log_for_person",
                                                   {"name": "Wren Alder", "they_said_no": True}))
        assert r["success"], "please don't can still be recorded with lookups off"
    import features
    assert features.LEVERS["person_lookup"].default is True


def test_its_name_cant_be_mistaken_for_her_memory():
    names = {t["name"] for t in PERSON_LOOKUP_TOOLS}
    assert names == {"public_lookup_person", "lookup_log_for_person"}
    desc = next(t for t in PERSON_LOOKUP_TOOLS if t["name"] == "public_lookup_person")["description"]
    assert desc.startswith("Public lookup:") and "This is not lookup_person" in desc.split("\n")[0]
    assert "keep_off" in desc and "reads the handles your PeopleDex already holds" in desc
    assert pl.wants_lookup_tools("could you do a public lookup on her?")
