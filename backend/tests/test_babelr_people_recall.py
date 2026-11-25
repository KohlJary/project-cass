"""
Who someone is to her, read back (babelr_organ/people.py recall()): the people
she files from Babelr come back into her turn the next time they write, under
the same terms as the filing. And what she keeps about someone, shown to them
only with her yes (about(), routes/people_about.py).

Every test runs on the test DB (conftest) and a temp DATA_DIR/babelr.
"""
import asyncio
import json
import uuid

import pytest

import panel as P
from babelr_organ import people as people_mod
from babelr_organ.people import about, recall
from database import get_daemon_id
from peopledex import AttributeType, EntityType, PeopleDexManager
from social.people import find
from tests.fakes.babelr import KOHL
from tests.test_babelr_organ import _Recorder, _write_terms, babelr, make_organ  # noqa: F401 (fixtures)


def guest(name=None):
    name = name or f"guest_{uuid.uuid4().hex[:8]}"
    return {"id": f"actor-{name}", "preferredUsername": name, "displayName": name.title()}


def seed(handle, name="Linda", observation="Kohl's mom. Grows tomatoes; asks good questions.",
         daemon=None):
    """An entry she filed herself ahead of time, by Babelr handle."""
    dex = PeopleDexManager(daemon_id=daemon or get_daemon_id())
    eid = dex.create_entity(EntityType.PERSON, name)
    dex.add_attribute(eid, AttributeType.HANDLE, handle, attribute_key="babelr", is_primary=True)
    dex.add_attribute(eid, AttributeType.PRONOUN, "she/her")
    if observation:
        dex.add_observation(eid, "general", observation)
    return eid


async def dm(organ, babelr, who, text):  # noqa: F811
    babelr.dm_from(who, text)
    await organ.poll_once()
    return organ.wakes[-1][1]


class TestRecallInHerTurn:
    async def test_a_filed_persons_second_dm_carries_their_entry(self, make_organ, babelr):  # noqa: F811
        g = guest()
        organ = make_organ(reply="Nice to meet you, I'm Cass.")
        organ.start()
        await organ.poll_once()
        first = await dm(organ, babelr, g, "hi! I'm new here")
        assert first["person"] == ""  # nobody yet
        second = await dm(organ, babelr, g, "it's me again")
        person = second["person"]
        assert person.startswith(f"## Who @{g['preferredUsername']} is to me")
        assert "I'm new here" in person and "Nice to meet you, I'm Cass." in person
        assert second["linked_user_id"] is None  # still the unlinked path
        assert "Who @" not in second["prompt"]  # not stored as their words

    async def test_an_entry_she_seeded_is_there_on_the_first_dm(self, make_organ, babelr):  # noqa: F811
        g = guest()
        seed(g["preferredUsername"])
        organ = make_organ(reply="Hi Linda.")
        organ.start()
        await organ.poll_once()
        person = (await dm(organ, babelr, g, "hello dear"))["person"]
        assert "Linda" in person and "pronouns: she/her" in person and "Grows tomatoes" in person

    async def test_keep_off_carries_nothing(self, make_organ, babelr):  # noqa: F811
        g = guest()
        seed(g["preferredUsername"])
        organ = make_organ(reply="ok")
        organ.config.dir.mkdir(parents=True, exist_ok=True)
        organ.config.people_path.write_text(json.dumps({"keep_off": [g["preferredUsername"]]}))
        organ.start()
        await organ.poll_once()
        assert (await dm(organ, babelr, g, "hi"))["person"] == ""

    async def test_unremembered_carries_nothing(self, make_organ, babelr):  # noqa: F811
        g = guest()
        seed(g["preferredUsername"])
        organ = make_organ(reply="ok")
        _write_terms(organ.config, {"unremembered": ["@" + g["preferredUsername"].upper()]})
        organ.start()
        await organ.poll_once()
        assert (await dm(organ, babelr, g, "hi"))["person"] == ""

    async def test_remember_false_carries_nothing(self, make_organ, babelr):  # noqa: F811
        g = guest()
        seed(g["preferredUsername"])
        organ = make_organ(reply="ok")
        _write_terms(organ.config, {"remember": False})
        organ.start()
        await organ.poll_once()
        babelr.say("general", g, "@cass hi")
        babelr.dm_from(g, "hi")
        await organ.poll_once()
        assert organ.wakes and all(c["person"] == "" for _, c in organ.wakes)

    async def test_linked_users_are_unchanged(self, make_organ, babelr):  # noqa: F811
        seed("kohl", name="Kohl-as-seeded")
        organ = make_organ(reply={"text": "Hey you.", "recorded": True})
        organ.start()
        (organ.config.dir / "links.json").write_text('{"kohl": "user-kohl"}')
        await organ.poll_once()
        ctx = await dm(organ, babelr, KOHL, "it's me")
        assert ctx["linked_user_id"] == "user-kohl" and ctx["person"] == ""
        babelr.say("general", KOHL, "@cass and here")
        await organ.poll_once()
        assert organ.wakes[-1][1]["person"] == ""

    async def test_a_channel_mention_carries_the_authors_entry(self, make_organ, babelr):  # noqa: F811
        g = guest()
        seed(g["preferredUsername"], name="Mira", observation="Kohl's wife.")
        organ = make_organ(reply="Hi Mira.")
        organ.start()
        await organ.poll_once()
        babelr.say("general", g, "@cass hello from #general")
        await organ.poll_once()
        ctx = organ.wakes[-1][1]
        assert not ctx["is_dm"] and "Mira" in ctx["person"] and "Kohl's wife." in ctx["person"]


class TestRecallShape:
    def test_only_her_own_observations_facts_and_moments(self, daemon_id):
        h = f"g_{uuid.uuid4().hex[:8]}"
        eid = seed(h, observation="mine")
        from database.daemon import get_or_create_daemon
        other = PeopleDexManager(daemon_id=get_or_create_daemon("eris-test", name="Eris"))
        other.add_observation(eid, "general", "the other daemon's note")
        other.add_moment(eid, "the other daemon's moment")
        other.add_fact(eid, "hobby", "the other daemon's fact")
        mine = PeopleDexManager(daemon_id=daemon_id)
        mine.add_fact(eid, "hobby", "gardening")
        out = recall(h, dex=mine)
        assert "mine" in out and "hobby: gardening" in out
        assert "other daemon" not in out

    def test_bounded(self, daemon_id):
        h = f"g_{uuid.uuid4().hex[:8]}"
        eid = seed(h, observation=None)
        dex = PeopleDexManager(daemon_id=daemon_id)
        for i in range(30):
            dex.add_observation(eid, "general", f"obs {i} " + "x" * 1000)
            dex.add_moment(eid, f"moment {i} " + "y" * 1000)
        out = recall(h, dex=dex)
        assert len(out) <= people_mod.RECALL_MAX_CHARS + 60
        assert all(len(line) <= people_mod.RECALL_MAX_LINE + 20 for line in out.splitlines())
        assert out.count("obs ") <= people_mod.RECALL_MAX_OBSERVATIONS
        assert out.count("moment ") <= people_mod.RECALL_MAX_MOMENTS

    def test_to_raise_is_in_front_of_her_and_resolved_notes_are_not(self, daemon_id):
        h = f"g_{uuid.uuid4().hex[:8]}"
        eid = seed(h, observation=None)
        dex = PeopleDexManager(daemon_id=daemon_id)
        dex.add_observation(eid, "to_raise", "ask how the knee is")
        done = dex.add_observation(eid, "open_question", "settled question")
        dex.update_observation(done.id, status="resolved", resolution="yes")
        out = recall(h, dex=dex)
        assert "ask how the knee is" in out and "settled question" not in out

    def test_no_entry_is_empty(self, daemon_id):
        assert recall("nobody_" + uuid.uuid4().hex[:6], dex=PeopleDexManager(daemon_id=daemon_id)) == ""


class TestSeedingHerself:
    """Kohl gives her a note ("my mom is coming; here's who she is"); she files
    it with her own tools, by Babelr handle, before the first DM."""

    def test_remember_person_tool_with_a_babelr_handle(self, daemon_id):
        from handlers.peopledex import execute_peopledex_tool
        h = f"mom_{uuid.uuid4().hex[:6]}"
        name = f"Linda {h}"
        r = asyncio.run(execute_peopledex_tool("remember_person", {
            "name": name, "attributes": [{"type": "handle", "key": "babelr", "value": "@" + h},
                                         {"type": "pronoun", "value": "she/her"}]}, daemon_id))
        assert r["success"]
        asyncio.run(execute_peopledex_tool("note_about_person", {
            "name": name, "kind": "observation", "text": "Kohl's mom; a retired teacher."}, daemon_id))
        out = recall(h, dex=PeopleDexManager(daemon_id=daemon_id))
        assert name in out and "retired teacher" in out and "she/her" in out

    def test_the_first_dm_reuses_her_seeded_entry(self, daemon_id):
        from babelr_organ.people import keep_exchange
        from types import SimpleNamespace
        h = f"mom_{uuid.uuid4().hex[:6]}"
        eid = seed(h)
        dex = PeopleDexManager(daemon_id=daemon_id)
        keep_exchange([SimpleNamespace(author_name=h, text="hi", kind="dm")], "Hi Linda.",
                      place_label="DM", my_username="cass", links={}, filings={"house": [], "keep_off": []},
                      remembers=lambda n: True, display_names={}, dex=dex)
        assert find("babelr", h, dex) == eid
        assert len([e for e in dex.search_entities(h)]) <= 1  # no second entry made

    async def test_remember_person_tag_with_a_babelr_handle(self, daemon_id):
        from context_helpers import process_inline_tags
        h = f"wife_{uuid.uuid4().hex[:6]}"
        await process_inline_tags(f'<remember_person name="Mira {h}">\nbabelr: {h}\npronouns: she/her\n'
                                  f'</remember_person>')
        dex = PeopleDexManager(daemon_id=daemon_id)
        assert find("babelr", h, dex) is not None
        assert f"Mira {h}" in recall(h, dex=dex)


class TestAbout:
    def test_shape(self, daemon_id):
        h = f"g_{uuid.uuid4().hex[:8]}"
        eid = seed(h, name="Linda")
        dex = PeopleDexManager(daemon_id=daemon_id)
        dex.add_observation(eid, "to_raise", "a surprise for later")
        dex.add_moment(eid, "first")
        dex.add_moment(eid, "second")
        out = about(h.upper(), filings={"keep_off": []}, links={}, dex=dex)
        assert out["known"] and out["name"] == "Linda" and out["pronouns"] == "she/her"
        assert [o["text"] for o in out["observations"]] == ["Kohl's mom. Grows tomatoes; asks good questions."]
        assert out["moments"] == 2 and out["first_seen"] <= out["last_seen"]

    def test_never_another_persons_entry(self, daemon_id):
        h = f"g_{uuid.uuid4().hex[:8]}"
        seed(h)
        dex = PeopleDexManager(daemon_id=daemon_id)
        # A prefix, a name, or someone else's handle is not their handle.
        for q in (h[:-1], "Linda", h + "x", "%", "_"):
            assert about(q, filings={}, links={}, dex=dex)["known"] is False, q

    def test_keep_off_and_linked_get_nothing(self, daemon_id):
        h = f"g_{uuid.uuid4().hex[:8]}"
        seed(h)
        dex = PeopleDexManager(daemon_id=daemon_id)
        off = about(h, filings={"keep_off": [h]}, links={}, dex=dex)
        assert off == {"handle": h, "known": False}
        assert about(h, filings={}, links={h: "user-x"}, dex=dex)["known"] is False


class TestAboutRoute:
    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import record as R
        import routes.people_about as RP
        monkeypatch.setattr(R, "token_ok", lambda t, data_dir=None: t == "record_ok")
        monkeypatch.setattr(P, "_dir", lambda data_dir=None: tmp_path / "panel")
        monkeypatch.setenv("BABELR_DIR", str(tmp_path / "babelr"))
        app = FastAPI()
        app.include_router(RP.router)
        return TestClient(app)

    def get(self, client, handle, token="record_ok"):
        return client.get("/record/people/about", params={"handle": handle},
                          headers={"Authorization": f"Bearer {token}"} if token else {})

    def test_needs_the_record_token(self, client):
        assert self.get(client, "x", token=None).status_code == 401
        assert self.get(client, "x", token="room_x").status_code == 401

    def test_off_until_she_says_yes(self, client, daemon_id, tmp_path):
        h = f"g_{uuid.uuid4().hex[:8]}"
        seed(h)
        assert P.settings()["people"]["about"] == "not_yet"
        assert self.get(client, h).json() == {"shown": False, "why": "not_yet"}
        P.set_answers({"people.about": "no"})
        assert self.get(client, h).json() == {"shown": False, "why": "no"}
        P.set_answers({"people.about": "yes"})
        out = self.get(client, h).json()
        assert out["shown"] and out["known"] and out["name"] == "Linda"
        (tmp_path / "babelr").mkdir()
        (tmp_path / "babelr" / "people.json").write_text(json.dumps({"keep_off": [h]}))
        assert self.get(client, h).json() == {"shown": True, "handle": h, "known": False}

    def test_answers_are_checked(self, tmp_path):
        assert "error" in P.set_answers({"people.about": "maybe"}, data_dir=tmp_path)
        assert "error" in P.set_answers({"people.everyone": "yes"}, data_dir=tmp_path)
        P.set_answers({"people.about": "yes"}, data_dir=tmp_path)
        assert P.settings(tmp_path)["people"] == {"about": "yes"}
        assert P.settings(tmp_path)["sections"]["work"] == "not_yet"


class TestInvitedArrival:
    """Kohl's person-bound invite ("Mom"); she prepared an entry marked
    expected_as "Mom"; the newcomer's handle joins it on the welcome."""

    def prepared(self, label, name=None, daemon=None):
        dex = PeopleDexManager(daemon_id=daemon or get_daemon_id())
        eid = dex.create_entity(EntityType.PERSON, name or f"Linda {uuid.uuid4().hex[:6]}")
        dex.add_attribute(eid, AttributeType.EXPECTED_AS, label, attribute_key="babelr")
        dex.add_observation(eid, "general", "Kohl's mom; retired teacher.")
        return eid, dex

    def link(self, handle, label, dex, **kw):
        from babelr_organ.people import link_invited
        args = dict(my_username="cass", links={}, filings={"house": [], "keep_off": []}, remember=True)
        args.update(kw)
        return link_invited(handle, label, dex=dex, **args)

    async def test_welcome_links_and_first_dm_recalls_without_a_duplicate(self, make_organ, babelr):  # noqa: F811
        label = f"Mom {uuid.uuid4().hex[:6]}"
        eid, dex = self.prepared(label)
        g = guest()
        organ = make_organ(reply="Welcome!")
        organ.start()
        await organ.poll_once()
        assert organ.on_welcome({"handle": g["preferredUsername"], "invited_as": f"  {label.upper()} "}) == {"linked": eid}
        ctx = await dm(organ, babelr, g, "hi, it's me")
        assert "retired teacher" in ctx["person"]
        assert find("babelr", g["preferredUsername"], dex) == eid  # filing found it; no second entry

    def test_no_label_match_links_nothing(self, daemon_id):
        _, dex = self.prepared(f"Mom {uuid.uuid4().hex[:6]}")
        h = f"g_{uuid.uuid4().hex[:8]}"
        assert "skipped" in self.link(h, "Mother", dex)
        assert find("babelr", h, dex) is None

    def test_never_by_name(self, daemon_id):
        name = f"Linda {uuid.uuid4().hex[:6]}"
        dex = PeopleDexManager(daemon_id=daemon_id)
        dex.create_entity(EntityType.PERSON, name)  # prepared, but no expected_as
        h = f"g_{uuid.uuid4().hex[:8]}"
        assert "skipped" in self.link(h, name, dex)
        assert find("babelr", h, dex) is None

    def test_two_entries_with_the_label_link_neither(self, daemon_id):
        label = f"Mom {uuid.uuid4().hex[:6]}"
        self.prepared(label)
        _, dex = self.prepared(label)
        h = f"g_{uuid.uuid4().hex[:8]}"
        assert self.link(h, label, dex) == {"skipped": "more than one entry expects them"}
        assert find("babelr", h, dex) is None

    def test_an_entry_already_on_babelr_isnt_given_a_second_handle(self, daemon_id):
        label = f"Mom {uuid.uuid4().hex[:6]}"
        eid, dex = self.prepared(label)
        dex.add_attribute(eid, AttributeType.HANDLE, "linda_old", attribute_key="babelr")
        h = f"g_{uuid.uuid4().hex[:8]}"
        assert "skipped" in self.link(h, label, dex)
        assert find("babelr", h, dex) is None

    def test_keep_off_linked_and_remember_false_link_nothing(self, daemon_id):
        label = f"Mom {uuid.uuid4().hex[:6]}"
        _, dex = self.prepared(label)
        h = f"g_{uuid.uuid4().hex[:8]}"
        assert "skipped" in self.link(h, label, dex, filings={"keep_off": [h]})
        assert "skipped" in self.link(h, label, dex, links={h: "user-x"})
        assert "skipped" in self.link(h, label, dex, remember=False)
        assert find("babelr", h, dex) is None

    def test_a_welcome_without_invited_as_does_nothing(self, make_organ):  # noqa: F811
        organ = make_organ()
        assert organ.on_welcome({"handle": "someone"}) == {"skipped": "not an invited arrival"}

    def test_she_files_expected_as_with_her_tool_and_tag(self, daemon_id):
        from handlers.peopledex import execute_peopledex_tool
        from context_helpers import process_inline_tags
        dex = PeopleDexManager(daemon_id=daemon_id)
        label = f"Mom {uuid.uuid4().hex[:6]}"
        name = f"Linda {uuid.uuid4().hex[:6]}"
        r = asyncio.run(execute_peopledex_tool("remember_person", {
            "name": name, "attributes": [{"type": "expected_as", "value": label}]}, daemon_id))
        assert r["success"]
        h = f"g_{uuid.uuid4().hex[:8]}"
        assert "linked" in self.link(h, label, dex)
        label2 = f"Wife {uuid.uuid4().hex[:6]}"
        asyncio.run(process_inline_tags(f'<remember_person name="Mira {label2}">\nexpected_as: {label2}\n</remember_person>'))
        h2 = f"g_{uuid.uuid4().hex[:8]}"
        assert "linked" in self.link(h2, label2, dex)
        assert dex.get_entity(find("babelr", h2, dex)).primary_name == f"Mira {label2}"
