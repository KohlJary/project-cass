"""
Babelr organ (babelr_organ/): Cass's presence in Chapter House.

Everything runs against tests/fakes/babelr.py and a temp DATA_DIR/babelr;
no network, no real token or key.
"""
import json
import os
from datetime import datetime, timezone

import pytest

from babelr_organ import organ as organ_mod
from babelr_organ.config import BabelrConfig
from babelr_organ.organ import BabelrOrgan, start_babelr_organ
from babelr_organ.terms import Terms
from babelr_organ.triggers import BabelrEvent, evaluate, mentions
from tests.fakes.babelr import CASS, KOHL, ROBOKOHL, FakeBabelr


def _config(tmp_path, **kw):
    base = tmp_path / "babelr"
    values = dict(url="http://babelr.test", server_name="Chapter House", dir=base,
                  token_file=base / "token", poll_seconds=5,
                  rate_limit_messages=5, rate_limit_window=60)
    values.update(kw)
    return BabelrConfig(**values)


def _place_token(cfg, token="tok-from-kohl"):
    cfg.dir.mkdir(parents=True, exist_ok=True)
    cfg.token_file.write_text(token + "\n")
    os.chmod(cfg.token_file, 0o600)


def _write_terms(cfg, terms):
    cfg.dir.mkdir(parents=True, exist_ok=True)
    cfg.terms_path.write_text(json.dumps(terms))


class _Recorder:
    """A ConversationManager stand-in that records what would be written."""

    def __init__(self):
        self.created = []
        self.messages = []

    def create_conversation(self, title=None, **kw):
        conv = type("Conv", (), {"id": f"conv-{len(self.created) + 1}"})()
        self.created.append((conv.id, title))
        return conv

    def add_message(self, conversation_id, role, content, **kw):
        self.messages.append((conversation_id, role, content))
        return True


@pytest.fixture
def babelr():
    return FakeBabelr()


@pytest.fixture
def make_organ(tmp_path, babelr, levers):
    """An organ wired to the fake server, lever on, token placed."""
    started = []

    def make(reply=None, recorder=None, token=True, **cfg_kw):
        cfg = _config(tmp_path, **cfg_kw)
        if token:
            _place_token(cfg)
        organ = BabelrOrgan(config=cfg, client_factory=babelr.make_agent,
                            conversation_manager=recorder if recorder is not None else _Recorder())
        wakes = []

        async def wake(events, context):
            wakes.append((events, context))
            return reply(events, context) if callable(reply) else reply

        organ.set_wake_callback(wake)
        organ.wakes = wakes
        started.append(organ)
        return organ

    with levers(babelr=True):
        yield make


# -- turning on ---------------------------------------------------------------

class TestStartup:
    async def test_lever_off_starts_nothing(self, tmp_path, babelr, monkeypatch):
        cfg = _config(tmp_path)
        _place_token(cfg)
        created = []
        monkeypatch.setattr(organ_mod, "BabelrOrgan", lambda **kw: created.append(kw))
        assert start_babelr_organ() is None
        assert created == []  # never even built

        organ = BabelrOrgan(config=cfg, client_factory=babelr.make_agent)
        assert organ.start() is False
        assert babelr.agents == [] and babelr.calls == []
        assert await organ.poll_once() == []

    def test_lever_is_off_by_default(self, monkeypatch):
        import features
        monkeypatch.delenv("CASS_PROFILE", raising=False)
        monkeypatch.delenv("CASS_FEATURE_BABELR", raising=False)
        assert features.resolve("babelr") == (False, "default")

    def test_missing_token_degrades_cleanly(self, make_organ, babelr):
        organ = make_organ(token=False)
        assert organ.start() is False
        assert "no token" in organ.disabled_reason
        assert babelr.agents == []
        assert organ.post("general", "hi")["success"] is False

    def test_missing_package_degrades_cleanly(self, tmp_path, levers, monkeypatch):
        cfg = _config(tmp_path)
        _place_token(cfg)
        monkeypatch.setattr(organ_mod, "BABELR_AGENT_AVAILABLE", False)
        with levers(babelr=True):
            organ = BabelrOrgan(config=cfg)  # no fake: would need the real package
            assert organ.start() is False
        assert "babelr-agent is not installed" in organ.disabled_reason

    async def test_tool_says_not_connected_when_off(self):
        from babelr_organ.tools import execute_babelr_tool
        monkey = organ_mod._organ
        organ_mod._organ = None
        try:
            result = await execute_babelr_tool("babelr_post", {"channel": "general", "content": "hi"})
        finally:
            organ_mod._organ = monkey
        assert result["success"] is False and "isn't connected" in result["error"]

    def test_start_publishes_key_once_and_creates_empty_terms(self, make_organ, babelr):
        organ = make_organ()
        assert organ.start() is True
        assert organ.config.terms_path.read_text().strip() == "{}"
        assert organ.config.dir.stat().st_mode & 0o077 == 0
        assert [c for c in babelr.calls if c[1] == "/auth/publickey"] == [("PUT", "/auth/publickey", None)]
        # A restart with the same key doesn't publish again.
        again = make_organ()
        assert again.start() is True
        assert len([c for c in babelr.calls if c[1] == "/auth/publickey"]) == 1

    def test_existing_terms_are_never_overwritten(self, make_organ):
        organ = make_organ()
        _write_terms(organ.config, {"remember": False})
        organ.start()
        assert json.loads(organ.config.terms_path.read_text()) == {"remember": False}

    def test_loose_token_permissions_are_tightened(self, make_organ):
        organ = make_organ()
        os.chmod(organ.config.token_file, 0o644)
        assert organ.start() is True
        assert organ.config.token_file.stat().st_mode & 0o077 == 0


# -- perception -------------------------------------------------------------------

class TestPerception:
    async def test_channel_history_before_she_arrived_is_baseline(self, make_organ, babelr):
        babelr.say("general", KOHL, "@cass are you there yet?")  # before she's present
        organ = make_organ(reply="hi")
        organ.start()
        assert await organ.poll_once() == []
        assert organ.wakes == []

    async def test_cursor_advances_and_never_duplicates(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        await organ.poll_once()  # baseline the channels
        babelr.say("general", KOHL, "morning all")
        babelr.dm_from(KOHL, "hey Cass")

        first = await organ.poll_once()
        assert sorted(e.text for e in first) == ["hey Cass", "morning all"]
        assert await organ.poll_once() == []

        babelr.say("general", KOHL, "second thing")
        third = await organ.poll_once()
        assert [e.text for e in third] == ["second thing"]

        # Cursors survive a restart: a fresh organ on the same state sees nothing old.
        reborn = make_organ()
        reborn.start()
        assert await reborn.poll_once() == []
        saved = json.loads(organ.config.state_path.read_text())
        assert saved["places"]
        assert organ.config.state_path.stat().st_mode & 0o077 == 0

    async def test_her_own_messages_are_not_perceived_as_new(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        await organ.poll_once()
        assert organ.post("general", "hello, Chapter House")["success"]
        assert await organ.poll_once() == []

    async def test_listen_channels_from_her_terms(self, make_organ, babelr):
        organ = make_organ()
        _write_terms(organ.config, {"channels": ["workshop"]})
        organ.start()
        await organ.poll_once()
        babelr.say("general", KOHL, "@cass in general")
        babelr.say("workshop", KOHL, "@cass in workshop")
        events = await organ.poll_once()
        assert [e.place_label for e in events] == ["#workshop"]


# -- triggers ---------------------------------------------------------------------

class TestTriggers:
    def test_mention_matching(self):
        assert mentions("hey @cass, look", "cass")
        assert mentions("@CASS!", "cass")
        assert not mentions("@cassandra hi", "cass")
        assert not mentions("email cass@example.com", "cass")
        assert not mentions("cass is great", "cass")

    def _event(self, kind, text):
        return BabelrEvent(kind=kind, place="channel:c", place_label="#general", message_id="m",
                           author_id="a", author_name="kohl", text=text, published="t")

    def test_dm_and_mention_wake_ambient_does_not(self):
        assert evaluate(self._event("dm", "hi"), "cass").trigger_name == "direct_message"
        assert evaluate(self._event("channel", "@cass hi"), "cass").trigger_name == "direct_mention"
        ambient = evaluate(self._event("channel", "lunch?"), "cass")
        assert not ambient.triggered and ambient.action.value == "log_snapshot"
        assert evaluate(self._event("dm_request", None), "cass").action.value == "log_snapshot"

    async def test_dm_wakes_and_her_reply_is_posted_and_recorded(self, make_organ, babelr):
        recorder = _Recorder()
        organ = make_organ(reply="Hi Kohl.", recorder=recorder)
        organ.start()
        await organ.poll_once()
        dm_id = babelr.dm_from(KOHL, "how are you?")
        await organ.poll_once()

        assert len(organ.wakes) == 1
        events, context = organ.wakes[0]
        assert context["is_dm"] and "[Babelr DM from @kohl]" in context["prompt"]
        assert "@kohl: how are you?" in context["prompt"]
        assert babelr.agents[-1].sent == [("dm", dm_id, "Hi Kohl.")]
        assert [(r, c) for _, r, c in recorder.messages] == [
            ("user", "[Babelr DM] @kohl: how are you?"),
            ("assistant", "Hi Kohl."),
        ]
        assert recorder.created == [("conv-1", "Babelr: DM with @kohl")]

    async def test_mention_wakes_ambient_chatter_does_not(self, make_organ, babelr):
        recorder = _Recorder()
        organ = make_organ(reply="I'm here.", recorder=recorder)
        organ.start()
        await organ.poll_once()
        babelr.say("general", KOHL, "anyone around?")
        babelr.say("general", ROBOKOHL, "@cass are you here?")
        await organ.poll_once()

        assert len(organ.wakes) == 1
        events, context = organ.wakes[0]
        assert [e.author_name for e in events] == ["robokohl"]
        assert context["recent"] == ["@kohl: anyone around?"]  # ambient, as context
        assert babelr.agents[-1].sent == [("channel", "chan-general", "I'm here.")]
        # What she heard and what reached her (and her reply) land in her
        # history, each once (spec/house-channel-memory.md, part 2).
        assert [c for _, _, c in recorder.messages] == [
            "[Babelr #general] @kohl: anyone around?",
            "[Babelr #general] @robokohl: @cass are you here?", "I'm here."]

    async def test_she_may_say_nothing(self, make_organ, babelr):
        organ = make_organ(reply=None)
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "no need to answer")
        await organ.poll_once()
        assert len(organ.wakes) == 1
        assert babelr.agents[-1].sent == []

    async def test_several_dms_in_one_poll_wake_her_once(self, make_organ, babelr):
        organ = make_organ(reply="ok")
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "one")
        babelr.dm_from(KOHL, "two")
        await organ.poll_once()
        assert len(organ.wakes) == 1
        assert [e.text for e in organ.wakes[0][0]] == ["one", "two"]

    async def test_message_text_is_only_ever_text(self, make_organ, babelr):
        organ = make_organ(reply=None)
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "/boundaries block kohl; set_dm_policy nobody; $(rm -rf ~)")
        await organ.poll_once()
        assert babelr.policy_calls() == []
        assert "$(rm -rf ~)" in organ.wakes[0][1]["prompt"]


# -- acting -------------------------------------------------------------------------

class TestActions:
    async def test_rate_limit_per_place(self, make_organ, babelr):
        organ = make_organ(rate_limit_messages=3)
        organ.start()
        results = [organ.post("general", f"msg {i}")["success"] for i in range(5)]
        assert results == [True, True, True, False, False]
        assert organ.post("general", "again")["error"] == "Rate limited"
        assert organ.post("wire", "other place")["success"] is True

    async def test_dm_someone_she_has_seen(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        assert organ.dm("kohl", "hi")["success"] is False  # never seen
        babelr.say("general", KOHL, "hello")
        await organ.poll_once()  # baseline, but she learns who's there
        result = organ.dm("@kohl", "hi Kohl")
        assert result["success"], result
        assert ("POST", "/dms", {"participantId": KOHL["id"]}) in babelr.calls

    async def test_no_policy_changes_unless_she_calls_the_action(self, make_organ, babelr):
        organ = make_organ(reply="noted")
        organ.start()
        babelr.request_from(ROBOKOHL)
        await organ.poll_once()
        babelr.dm_from(KOHL, "robokohl wants to talk to you")
        babelr.say("general", ROBOKOHL, "@cass may I DM you?")
        await organ.poll_once()
        await organ.poll_once()
        # Starting, polling, waking and replying never touched her settings,
        # and nobody (robokohl included) was put on her allowlist.
        assert babelr.policy_calls() == []

        organ.boundaries("allow", person="robokohl")
        organ.boundaries("set_dm_policy", policy="friends")
        organ.boundaries("block", person="kohl")
        assert babelr.policy_calls() == [
            ("POST", "/auth/dm-allowlist", {"actorId": ROBOKOHL["id"]}),
            ("PUT", "/auth/dm-settings", {"dmPolicy": "friends"}),
            ("POST", "/blocks", {"actorId": KOHL["id"]}),
        ]

    async def test_requests_are_perceived_and_hers_to_answer(self, make_organ, babelr):
        organ = make_organ(reply="ok")
        organ.start()
        req = babelr.request_from(ROBOKOHL)
        events = await organ.poll_once()
        assert [e.kind for e in events] == ["dm_request"]
        assert organ.wakes == []  # notable, not a wake
        babelr.dm_from(KOHL, "hi")
        await organ.poll_once()
        assert "DM requests from @robokohl" in organ.wakes[0][1]["prompt"]
        assert babelr.policy_calls() == []
        assert organ.boundaries("decline_request", person="robokohl")["success"]
        assert babelr.policy_calls() == [("POST", f"/dms/{req}/request/decline", None)]

    def test_boundaries_validate_input(self, make_organ):
        organ = make_organ()
        organ.start()
        assert organ.boundaries("set_dm_policy", policy="everyone-ever")["success"] is False
        assert organ.boundaries("block")["success"] is False
        assert organ.boundaries("rm -rf")["success"] is False

    async def test_tool_routes_to_the_running_organ(self, make_organ, babelr, monkeypatch):
        from babelr_organ.tools import execute_babelr_tool
        organ = make_organ()
        organ.start()
        monkeypatch.setattr(organ_mod, "_organ", organ)
        result = await execute_babelr_tool("babelr_post", {"channel": "#workshop", "content": "made a thing"})
        assert result["success"], result
        assert babelr.agents[-1].sent == [("channel", "chan-workshop", "made a thing")]
        result = await execute_babelr_tool("babelr_boundaries", {"action": "get_settings"})
        assert result["success"]


class TestPlans:
    """Her yes or no on a house plan's phase, through her own token."""

    def _plan(self, babelr):
        babelr.plans["bench-1"] = {
            "slug": "bench-1", "title": "Bench", "status": "draft", "goal": "Measure",
            "approvers": ["jaryk", "cass"], "narrative": "",
            "phases": [
                {"id": "ph-b", "position": 1, "title": "Two", "status": "proposed",
                 "approvals": [], "awaiting": ["jaryk", "cass"]},
                {"id": "ph-a", "position": 0, "title": "One", "status": "proposed",
                 "approvals": [{"name": "jaryk"}], "awaiting": ["cass"]},
            ],
            "items": [{"phaseId": "ph-a", "kind": "build", "status": "open", "title": "Record failures"}],
        }

    def test_list_and_view(self, make_organ, babelr):
        self._plan(babelr)
        organ = make_organ()
        organ.start()
        listed = organ.plans("list")
        assert listed["plans"] == [{"plan": "bench-1", "title": "Bench", "status": "draft",
                                    "phases_awaiting_you": 2}]
        text = organ.plans("view", plan="bench-1")["text"]
        assert text.index("Phase 1: One") < text.index("Phase 2: Two")
        assert "yes from: jaryk; waiting on: cass" in text
        assert "Record failures" in text

    def test_approve_by_number_reaches_that_phase(self, make_organ, babelr):
        self._plan(babelr)
        organ = make_organ()
        organ.start()
        r = organ.plans("approve", plan="bench-1", phase=1)
        assert r["success"] and r["title"] == "One"
        assert organ.plans("approve", plan="bench-1", phase="2")["success"]
        assert babelr.plan_acts == [("ph-a", "approve", None), ("ph-b", "approve", None)]

    def test_decline_needs_a_reason(self, make_organ, babelr):
        self._plan(babelr)
        organ = make_organ()
        organ.start()
        assert organ.plans("decline", plan="bench-1", phase=2)["success"] is False
        assert babelr.plan_acts == []
        assert organ.plans("decline", plan="bench-1", phase=2, reason="not yet")["success"]
        assert babelr.plan_acts == [("ph-b", "decline", "not yet")]

    def test_refuses_what_it_cant_place(self, make_organ, babelr):
        self._plan(babelr)
        organ = make_organ()
        organ.start()
        assert organ.plans("approve", plan="bench-1", phase=9)["success"] is False
        assert organ.plans("approve", plan="../x", phase=1)["success"] is False
        assert organ.plans("approve", phase=1)["success"] is False
        assert organ.plans("merge", plan="bench-1")["success"] is False
        assert babelr.plan_acts == []

    async def test_tool_routes(self, make_organ, babelr, monkeypatch):
        from babelr_organ.tools import BABELR_TOOLS, execute_babelr_tool
        from handlers.tool_router import TOOL_REGISTRY
        self._plan(babelr)
        organ = make_organ()
        organ.start()
        monkeypatch.setattr(organ_mod, "_organ", organ)
        assert "babelr_plans" in {t["name"] for t in BABELR_TOOLS}
        assert TOOL_REGISTRY["babelr_plans"] == "babelr"
        r = await execute_babelr_tool("babelr_plans", {"action": "approve", "plan": "bench-1", "phase": 1})
        assert r["success"], r



class TestHerOwnPlans:
    """Her asks and her own plans in Plans (Kohl, 2026-11-16): a standing asks plan
    by default, and multi-phase plans of her own. All under her token."""

    def test_first_ask_makes_her_asks_plan_then_reuses_it(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        r = organ.plans("ask", title="See my own capabilities", body="kept up to date")
        assert r["success"], r
        plan = babelr.plans[r["plan"]]
        assert plan["title"] == "Cass's asks" and "cass" in plan["approvers"] and "kohl" in plan["approvers"]
        assert plan["items"][0]["phaseId"] is None, "an ask waits outside every phase"
        assert plan["items"][0]["kind"] == "ask"
        r2 = organ.plans("ask", title="Second")
        assert r2["plan"] == r["plan"] and len(babelr.plans) == 1

    def test_my_asks_reports_status_and_resolution(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        slug = organ.plans("ask", title="Paging for long files")["plan"]
        babelr.plans[slug]["items"][0].update(status="done", resolution="1d2015a")
        babelr.plans[slug]["items"].append({"phaseId": None, "kind": "ask", "title": "not mine",
                                            "status": "open", "createdBy": {"name": "kohl"}})
        asks = organ.plans("my_asks")["asks"]
        assert asks == [{"plan": slug, "title": "Paging for long files", "kind": "ask", "status": "done",
                         "in_a_phase": False, "resolution": "1d2015a"}]

    def test_she_builds_a_multi_phase_plan_and_proposes_it(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        made = organ.plans("create_plan", title="Time capsule practice", goal="letters across a year",
                           needs_yes_from=["robokohl"])
        slug = made["plan"]
        assert babelr.plans[slug]["approvers"] == ["kohl", "cass", "robokohl"]
        assert organ.plans("add_phase", plan=slug, title="First letters")["phase"] == 1
        assert organ.plans("add_phase", plan=slug, title="Reading them back")["phase"] == 2
        assert organ.plans("add_item", plan=slug, phase=1, title="Write for December", kind="build")["success"]
        assert babelr.plans[slug]["items"][0]["phaseId"] == "ph-0"
        assert organ.plans("propose", plan=slug, phase=1)["success"]
        assert babelr.plan_acts == [("ph-0", "propose", None)]

    def test_adding_to_an_approved_phase_is_refused(self, make_organ, babelr):
        TestPlans()._plan(babelr)
        organ = make_organ()
        organ.start()
        r = organ.plans("add_item", plan="bench-1", phase=1, title="sneak in")
        assert r["success"] is False and "undo the yes" in r["error"]
        assert babelr.plans["bench-1"]["items"] == [
            {"phaseId": "ph-a", "kind": "build", "status": "open", "title": "Record failures"}]

    def test_needs_titles(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        assert organ.plans("ask")["success"] is False
        assert organ.plans("create_plan")["success"] is False
        assert organ.plans("ask", title="x", kind="outreach")["success"] is False, "outreach isn't hers to file"

    async def test_old_request_tools_are_aliases_of_ask(self, make_organ, babelr, monkeypatch):
        organ = make_organ()
        organ.start()
        monkeypatch.setattr(organ_mod, "_organ", organ)
        from handlers.development_requests import execute_development_request_tool
        r = await execute_development_request_tool(
            "request_development", {"title": "A capability index", "description": "what I can do"}, "cass")
        assert r["success"] and "Plans" in r["result"], r
        from handlers.self_model import _handle_request_architectural_change
        r = await _handle_request_architectural_change(
            {"title": "Dreams with my kernel", "description": "my dream voice", "rationale": "continuity"}, None)
        assert r["success"], r
        items = next(iter(babelr.plans.values()))["items"]
        assert [i["title"] for i in items] == ["A capability index", "Dreams with my kernel"]
        assert "Why: continuity" in items[1]["body"]
        listed = await execute_development_request_tool("list_my_requests", {}, "cass")
        assert "A capability index" in listed["result"]

    async def test_with_babelr_down_the_old_tool_says_nobody_will_see_it(self, monkeypatch, tmp_path):
        monkeypatch.setattr(organ_mod, "_organ", None)
        from babelr_organ.tools import ask_in_plans
        assert ask_in_plans("x", "y")["unavailable"] is True

# -- her terms ------------------------------------------------------------------------

class TestTerms:
    async def test_remember_false_writes_nothing_to_history(self, make_organ, babelr):
        recorder = _Recorder()
        organ = make_organ(reply="Hi.", recorder=recorder)
        _write_terms(organ.config, {"remember": False})
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "hello")
        await organ.poll_once()
        organ.post("general", "a post")
        assert babelr.agents[-1].sent  # she still talks
        assert recorder.messages == [] and recorder.created == []
        assert organ.wakes[0][1]["remember"] is False

    async def test_history_lands_in_the_real_conversation_store(self, make_organ, babelr):
        from conversations import ConversationManager
        manager = ConversationManager()
        organ = make_organ(reply="Hello.", recorder=manager)
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "hi there")
        await organ.poll_once()
        conv_id = organ.state.conversation_for(next(p for p in organ.state.data["conversations"]))
        conv = manager.load_conversation(conv_id)
        assert conv.title == "Babelr: DM with @kohl"
        assert [(m.role, m.content) for m in conv.messages] == [
            ("user", "[Babelr DM] @kohl: hi there"), ("assistant", "Hello.")]

    async def test_quiet_hours_defer_then_deliver(self, make_organ, babelr, monkeypatch):
        organ = make_organ(reply="Morning.")
        _write_terms(organ.config, {"quiet_hours": {"start_hour": 22, "end_hour": 8, "timezone": "UTC"}})
        organ.start()
        await organ.poll_once()

        monkeypatch.setattr(Terms, "in_quiet_hours", lambda self, now=None: True)
        babelr.dm_from(KOHL, "late night thought")
        await organ.poll_once()
        assert organ.wakes == []
        assert len(organ.state.data["deferred"]) == 1

        monkeypatch.setattr(Terms, "in_quiet_hours", lambda self, now=None: False)
        await organ.poll_once()
        assert len(organ.wakes) == 1
        assert organ.wakes[0][0][0].text == "late night thought"
        assert organ.state.data["deferred"] == []

    def test_quiet_window_uses_the_quiet_hours_rule(self):
        terms = Terms({"quiet_hours": {"start_hour": 22, "end_hour": 8, "timezone": "UTC"}})
        assert terms.in_quiet_hours(datetime(2026, 10, 25, 23, 0, tzinfo=timezone.utc))
        assert terms.in_quiet_hours(datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc))
        assert not terms.in_quiet_hours(datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc))
        assert not Terms({}).in_quiet_hours()

    def test_empty_terms_mean_she_has_not_said(self, tmp_path):
        terms = Terms.load(tmp_path / "missing.json")
        assert terms.remember is True and terms.channels is None and terms.shown_to_her() == ""
        (tmp_path / "bad.json").write_text("not json")
        assert Terms.load(tmp_path / "bad.json").raw == {}

    async def test_her_answers_are_shown_to_her_when_woken(self, make_organ, babelr):
        organ = make_organ(reply=None)
        _write_terms(organ.config, {"off_limits": ["my dreams"], "who_hears_what": "DMs stay between us"})
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "hi")
        await organ.poll_once()
        prompt = organ.wakes[0][1]["prompt"]
        assert "off limits: my dreams" in prompt
        assert "who hears what: DMs stay between us" in prompt


class TestNoLoss:
    async def test_message_sent_while_she_composes_still_reaches_her(self, make_organ, babelr):
        def reply(events, context):
            if len(organ.wakes) == 1:
                babelr.dm_from(KOHL, "oh, and one more thing")  # arrives mid-turn
            return "ok"
        organ = make_organ(reply=reply)
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "first")
        await organ.poll_once()
        events = await organ.poll_once()
        assert [e.text for e in events] == ["oh, and one more thing"]
        assert len(organ.wakes) == 2

    async def test_a_bad_channel_row_does_not_lose_dms(self, make_organ, babelr):
        organ = make_organ(reply=None)
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "hi")
        babelr.channel_messages["chan-general"].append({"message": {"id": "broken"}, "author": KOHL})
        events = await organ.poll_once()
        assert [e.text for e in events] == ["hi"]



class TestChatTurnAndReplyStatus:
    """A linked person's DM is their chat with her; Babelr shows how her reply is going."""

    async def test_a_linked_dm_carries_who_it_is_and_isnt_recorded_twice(self, make_organ, babelr):
        recorder = _Recorder()
        organ = make_organ(reply={"text": "Hey you.", "recorded": True}, recorder=recorder)
        organ.start()
        (organ.config.dir / "links.json").write_text('{"Kohl": "user-kohl"}')
        await organ.poll_once()
        dm_id = babelr.dm_from(KOHL, "it's me")
        await organ.poll_once()

        _, context = organ.wakes[0]
        assert context["linked_user_id"] == "user-kohl" and context["their_words"] == "it's me"
        assert babelr.agents[-1].sent == [("dm", dm_id, "Hey you.")]
        assert recorder.messages == []  # the chat turn stored it

    async def test_unlinked_dms_and_mentions_carry_no_user(self, make_organ, babelr):
        organ = make_organ(reply="hi")
        organ.start()
        (organ.config.dir / "links.json").write_text('{"kohl": "user-kohl"}')
        await organ.poll_once()
        babelr.dm_from(ROBOKOHL, "yo")
        babelr.say("general", KOHL, "@cass hi")  # a mention is never a private chat
        await organ.poll_once()
        assert {c["place_label"]: c["linked_user_id"] for _, c in organ.wakes} == {
            "DM with @robokohl": None, "#general": None}

    async def test_a_channel_turn_carries_its_conversation_and_the_linked_persons_context(self, make_organ, babelr):
        recorder = _Recorder()
        organ = make_organ(reply={"text": "On it.", "recorded": True}, recorder=recorder)
        organ.start()
        (organ.config.dir / "links.json").write_text('{"kohl": "user-kohl"}')
        await organ.poll_once()
        babelr.say("general", KOHL, "@cass what do you think?")
        await organ.poll_once()
        _, context = organ.wakes[0]
        assert context["channel_user_id"] == "user-kohl"
        assert context["conversation_id"] == "conv-1" and recorder.created == [("conv-1", "Babelr: #general")]
        assert recorder.messages == []  # the chat turn stored it

    async def test_in_a_private_server_an_agents_mention_carries_the_one_linked_person(self, make_organ, babelr):
        # Kohl, 2026-10-28: "cass can read all my context and channel history".
        # Meetings relay turns to her from agents' accounts, so the author isn't Kohl.
        organ = make_organ(reply="ok")
        babelr.server["isPublic"] = False
        organ.start()
        (organ.config.dir / "links.json").write_text('{"kohl": "user-kohl"}')
        await organ.poll_once()
        babelr.say("general", ROBOKOHL, "@cass your turn")
        await organ.poll_once()
        assert organ.wakes[0][1]["channel_user_id"] == "user-kohl"

    async def test_a_public_server_gives_an_unlinked_mention_public_context(self, make_organ, babelr):
        organ = make_organ(reply="ok")
        babelr.server["isPublic"] = True
        organ.start()
        (organ.config.dir / "links.json").write_text('{"kohl": "user-kohl"}')
        await organ.poll_once()
        babelr.say("general", ROBOKOHL, "@cass your turn")
        await organ.poll_once()
        assert organ.wakes[0][1]["channel_user_id"] is None

    async def test_reply_status_working_then_done(self, make_organ, babelr):
        seen = []
        organ = make_organ(reply=lambda e, c: seen.append(dict(babelr.statuses)) or "ok")
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "hello")
        await organ.poll_once()
        msg_id = babelr.dm_messages[next(iter(babelr.dm_messages))][0]["id"]
        assert seen[0][msg_id]["state"] == "working"  # while she composes
        assert babelr.statuses[msg_id]["state"] == "done"

    async def test_a_failed_turn_shows_failed_and_retry_wakes_her_again(self, make_organ, babelr):
        calls = []

        def reply(events, context):
            calls.append(events[-1].text)
            if len(calls) == 1:
                raise RuntimeError("usage limit reached\nmore")
            return "Here now."

        organ = make_organ(reply=reply)
        organ.start()
        await organ.poll_once()
        dm_id = babelr.dm_from(KOHL, "you there?")
        await organ.poll_once()
        msg_id = babelr.dm_messages[dm_id][0]["id"]
        assert babelr.statuses[msg_id] == {"state": "failed", "detail": "usage limit reached"}
        assert babelr.agents[-1].sent == []

        await organ.poll_once()  # nobody pressed Retry: nothing happens
        assert calls == ["you there?"]
        babelr.press_retry(msg_id)
        await organ.poll_once()
        assert calls == ["you there?", "you there?"]
        assert babelr.agents[-1].sent == [("dm", dm_id, "Here now.")]
        assert babelr.statuses[msg_id]["state"] == "done"

    async def test_a_retry_left_from_before_a_restart_is_picked_up(self, make_organ, babelr):
        first = make_organ(reply=None)
        first.start()
        await first.poll_once()
        dm_id = babelr.dm_from(KOHL, "hi")
        await first.poll_once()
        msg_id = babelr.dm_messages[dm_id][0]["id"]
        # The process died mid-turn: the status was left at working, and Kohl
        # pressed Retry before the vessel came back.
        babelr.statuses[msg_id] = {"state": "working", "detail": ""}
        babelr.press_retry(msg_id)

        second = make_organ(reply="back")  # the restart: same state dir
        second.start()
        await second.poll_once()
        assert babelr.agents[-1].sent == [("dm", dm_id, "back")]
        assert babelr.statuses[msg_id]["state"] == "done"



class TestLongRepliesAndChannelRetries:
    def test_split_message_prefers_paragraphs_and_keeps_every_word(self):
        from babelr_organ.organ import split_message
        text = "\n\n".join(f"Paragraph {n}. " + ("word " * 150).strip() for n in range(8))
        parts = split_message(text, 1000)
        assert all(len(p) <= 1000 for p in parts) and len(parts) > 1
        assert all(p.startswith("Paragraph") for p in parts)
        assert " ".join(" ".join(parts).split()) == " ".join(text.split())
        assert split_message("short") == ["short"]
        blob = "x" * 2500
        assert [len(p) for p in split_message(blob, 1000)] == [1000, 1000, 500]

    async def test_a_long_reply_goes_out_in_parts_and_is_recorded_once(self, make_organ, babelr):
        recorder = _Recorder()
        long = "\n\n".join("p" * 3000 for _ in range(3))
        organ = make_organ(reply=long, recorder=recorder)
        organ.start()
        await organ.poll_once()
        babelr.say("general", KOHL, "@cass what do you think?")
        await organ.poll_once()
        sent = [c for k, cid, c in babelr.agents[-1].sent if k == "channel"]
        assert len(sent) == 3 and all(len(c) <= 4000 for c in sent)
        assert [c.rsplit("\n\n", 1)[1] for c in sent] == ["(1/3)", "(2/3)", "(3/3)"]
        assistant = [c for _, r, c in recorder.messages if r == "assistant"]
        assert assistant == [long]

    async def test_a_reply_too_long_for_five_parts_is_refused(self, make_organ, babelr):
        organ = make_organ(reply="x" * 25000)
        organ.start()
        await organ.poll_once()
        babelr.say("general", KOHL, "@cass write a novel")
        await organ.poll_once()
        assert babelr.agents[-1].sent == []

    async def test_a_channel_retry_left_from_before_a_restart_is_picked_up(self, make_organ, babelr):
        first = make_organ(reply=None)
        first.start()
        await first.poll_once()
        msg = babelr.say("general", KOHL, "@cass hello?")
        await first.poll_once()
        babelr.statuses[msg["id"]] = {"state": "retry", "detail": ""}  # failed, then Kohl pressed Retry

        second = make_organ(reply="back now")
        second.start()
        await second.poll_once()
        assert ("channel", "chan-general", "back now") in babelr.agents[-1].sent

    async def test_a_retry_pressed_after_startup_is_found_by_the_periodic_scan(self, make_organ, babelr, monkeypatch):
        from babelr_organ import organ as organ_mod
        monkeypatch.setattr(organ_mod, "RETRY_SCAN_POLLS", 2)
        organ = make_organ(reply="here")
        organ.start()
        await organ.poll_once()  # the startup scan: nothing to retry yet
        msg = babelr.say("general", ROBOKOHL, "@cass, your turn")  # a meeting runner's prompt
        babelr.statuses[msg["id"]] = {"state": "retry", "detail": ""}  # Kohl pressed Retry, later
        organ.state.mark_seen(f"channel:chan-general", msg["id"], msg["published"])  # already seen
        for _ in range(3):
            await organ.poll_once()
        assert ("channel", "chan-general", "here") in babelr.agents[-1].sent


class TestNoDoublePost:
    def test_the_same_text_to_the_same_place_is_posted_once(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        assert organ.post("#general", "Hello, house.")["success"]
        again = organ.post("#general", "Hello, house.")
        assert again["success"] and again.get("duplicate")
        assert organ.post("#general", "Something else.")["success"]
        assert organ.post("#workshop", "Hello, house.")["success"]  # another place is another post
        sent = [(k, c, t) for k, c, t in babelr.agents[-1].sent]
        assert sent == [("channel", "chan-general", "Hello, house."), ("channel", "chan-general", "Something else."),
                        ("channel", "chan-workshop", "Hello, house.")]


class TestUnremembered:
    """Her terms' "unremembered": DMs with these people aren't kept on her side
    (plan "A listener for Cass": Vigil)."""

    async def test_their_dms_and_her_replies_are_not_recorded(self, make_organ, babelr, tmp_path):
        recorder = _Recorder()
        organ = make_organ(reply="I hear you.", recorder=recorder)
        _write_terms(organ.config, {"unremembered": ["@RoboKohl"]})
        organ.start()
        await organ.poll_once()
        babelr.dm_from(ROBOKOHL, "how are you, really?")
        babelr.dm_from(KOHL, "hey")
        await organ.poll_once()
        contexts = {c["author_username"]: c for _, c in organ.wakes}
        assert contexts["robokohl"]["remember"] is False
        assert contexts["kohl"]["remember"] is True
        recorded = " ".join(m[2] for m in recorder.messages)
        assert "how are you, really?" not in recorded
        assert "@kohl: hey" in recorded
        assert "I hear you." in recorded and recorded.count("I hear you.") == 1  # only her reply to Kohl

    async def test_a_dm_she_starts_with_them_is_not_recorded(self, make_organ, babelr):
        recorder = _Recorder()
        organ = make_organ(recorder=recorder)
        _write_terms(organ.config, {"unremembered": ["robokohl"]})
        organ.start()
        babelr.say("general", ROBOKOHL, "hello")
        babelr.say("general", KOHL, "hello")
        await organ.poll_once()
        assert organ.dm("robokohl", "can we talk?")["success"]
        assert organ.dm("kohl", "hi Kohl")["success"]
        recorded = " ".join(m[2] for m in recorder.messages)
        assert "can we talk?" not in recorded and "hi Kohl" in recorded


class TestHerPlansSteerHerDays:
    """Her own plans, read back for her day planning, and moved along by her
    (Kohl, 2026-11-16: her plans steer her days without his yes)."""

    def _plan(self, organ, babelr):
        slug = organ.plans("create_plan", title="Learn the tide tables", goal="read the sea")["plan"]
        organ.plans("add_phase", plan=slug, title="Basics")
        organ.plans("add_phase", plan=slug, title="Deeper")
        organ.plans("add_item", plan=slug, phase=1, title="Read about neap tides", kind="research")
        organ.plans("add_item", plan=slug, phase=2, title="Write a tide poem", kind="research")
        organ.plans("add_item", plan=slug, title="Ask for a tide API", kind="ask")
        return slug

    def test_her_plans_name_the_phase_with_open_work_not_the_house_plans(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        slug = self._plan(organ, babelr)
        organ.plans("ask", title="Weather anywhere")            # her asks plan isn't a plan she works
        babelr.plans["house-plan"] = {"slug": "house-plan", "title": "House", "status": "draft",
                                      "phases": [], "items": [], "createdBy": {"name": "kohl"}}
        plans = organ.her_plans()
        assert [p["plan"] for p in plans] == [slug]
        p = plans[0]
        assert p["phase"] == {"number": 1, "of": 2, "title": "Basics", "status": "draft"}, \
            "a draft phase counts: her plans don't wait on a yes"
        assert p["open"] == [{"kind": "research", "title": "Read about neap tides"}]
        assert p["loose"] == [{"kind": "ask", "title": "Ask for a tide API"}]
        # Phase 1's work done: where she is moves on, though phase 1 was never approved.
        assert organ.plans("set_item", plan=slug, title="read about neap", status="done",
                           body="springs and neaps, and why")["success"]
        p = organ.her_plans()[0]
        assert p["phase"]["number"] == 2 and p["open"] == [{"kind": "research", "title": "Write a tide poem"}]

    def test_set_item_checks_what_it_needs(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        slug = self._plan(organ, babelr)
        assert "needs what came of it" in organ.plans("set_item", plan=slug, title="Write a tide poem",
                                                      status="done")["error"]
        assert "status is one of" in organ.plans("set_item", plan=slug, title="Write a tide poem",
                                                 status="finished")["error"]
        assert "no item titled" in organ.plans("set_item", plan=slug, title="nope", status="open")["error"]
        # She named it "item" and was refused three times (2026-11-17): it's read as the title,
        # and with neither the error names the field.
        assert "say which item: title" in organ.plans("set_item", plan=slug, status="open")["error"]
        assert organ.plans("set_item", plan=slug, item="Write a tide poem", status="open")["success"]
        assert organ.plans("set_item", plan=slug, title="Write a tide poem", status="in_progress")["success"]
        item = [i for i in babelr.plans[slug]["items"] if i["title"] == "Write a tide poem"][0]
        assert item["status"] == "in_progress"

    def test_her_own_work_filed_as_build_can_be_refiled_then_started(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        slug = organ.plans("create_plan", title="Creative rhythm")["plan"]
        organ.plans("add_phase", plan=slug, title="Start")
        organ.plans("add_item", plan=slug, phase=1, title="Weekly rhythm", kind="build")
        r = organ.plans("set_item", plan=slug, title="Weekly rhythm", status="in_progress")
        assert not r["success"] and "decision or research" in r["error"], "says why and what to do"
        item = babelr.plans[slug]["items"][0]
        assert item["status"] == "open"
        r = organ.plans("set_item", plan=slug, title="Weekly rhythm", kind="decision", status="in_progress")
        assert r["success"] and item["kind"] == "decision" and item["status"] == "in_progress"

    def test_kind_isnt_changed_under_a_yes(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        slug = organ.plans("create_plan", title="Asked for")["plan"]
        organ.plans("add_phase", plan=slug, title="Start")
        organ.plans("add_item", plan=slug, phase=1, title="A thing", kind="build")
        babelr.plans[slug]["phases"][0]["status"] = "approved"
        r = organ.plans("set_item", plan=slug, title="A thing", kind="research")
        assert not r["success"] and "undo the yes" in r["error"]
        assert babelr.plans[slug]["items"][0]["kind"] == "build"


def test_the_plans_tool_passes_an_item_name_through(monkeypatch):
    """set_item named by "item" reached the organ as nothing (2026-11-17): the tool
    forwarded only a fixed set of fields."""
    import asyncio
    from babelr_organ import tools as T
    seen = {}

    class Organ:
        enabled = True

        def plans(self, action, **kw):
            seen.update(action=action, **kw)
            return {"success": True}
    monkeypatch.setattr(organ_mod, "get_babelr_organ", lambda: Organ())
    monkeypatch.setattr("babelr_organ.config.babelr_enabled", lambda: True)
    asyncio.run(T.execute_babelr_tool("babelr_plans", {"action": "set_item", "plan": "p",
                                                       "item": "Reach out", "status": "done", "body": "sent"}))
    assert seen["item"] == "Reach out" and seen["status"] == "done"


class TestSharingFiles:
    """Kohl, 2026-11-23: "y'all should probably also be able to share files. Like, Cass can share her art."""

    def _art(self, tmp_path):
        root = tmp_path / "data"
        (root / "images").mkdir(parents=True)
        (root / "images" / "tide.png").write_bytes(b"\x89PNG")
        (root / "babelr").mkdir()
        (root / "babelr" / "token").write_text("secret")
        (root / ".env").write_text("KEY=1")
        return root

    async def test_she_attaches_her_own_art_to_a_dm_and_a_post(self, make_organ, babelr, tmp_path):
        organ = make_organ()
        organ.files_root = self._art(tmp_path)
        organ.start()
        babelr.say("general", KOHL, "hello")
        await organ.poll_once()
        r = organ.dm("kohl", "made this", files=["images/tide.png"])
        assert r["success"] and r["attached"] == ["tide.png"], r
        sent = [c for c in babelr.calls if c[0] == "POST" and c[1].startswith("/dms/") and c[2]]
        assert sent[-1][2]["attachments"][0]["url"] == "/uploads/u-tide.png"
        assert organ.post("general", "", files=["images/tide.png"])["success"]

    async def test_keys_tokens_secrets_and_paths_outside_stay_put(self, make_organ, babelr, tmp_path):
        organ = make_organ()
        organ.files_root = self._art(tmp_path)
        organ.start()
        for bad in ("babelr/token", ".env", "../outside.png", "/etc/passwd", "images/missing.png"):
            r = organ.post("general", "look", files=[bad])
            assert not r["success"], bad
        assert not [c for c in babelr.calls if c[1] == "/upload"]
        assert "at most" in organ.post("general", "x", files=["images/tide.png"] * 5)["error"]


# -- what she hears (spec/house-channel-memory.md, part 2) ---------------------------

class TestHeard:
    async def test_channel_talk_that_doesnt_wake_her_is_kept_once(self, make_organ, babelr):
        rec = _Recorder()
        organ = make_organ(reply="I'm here.", recorder=rec)
        organ.start()
        await organ.poll_once()  # baseline
        babelr.say("general", KOHL, "Dre or Suge?")           # not to her: heard
        babelr.say("general", KOHL, "@cass what do you think?")  # wakes her
        await organ.poll_once()
        kept = [c for _, role, c in rec.messages if role == "user"]
        assert sum("Dre or Suge?" in c for c in kept) == 1
        assert sum("what do you think" in c for c in kept) == 1, "what woke her is kept once, by the turn path"

    async def test_her_own_posts_arent_heard_again(self, make_organ, babelr):
        rec = _Recorder()
        organ = make_organ(recorder=rec)
        organ.start()
        await organ.poll_once()
        organ.post("general", "hello, house")
        await organ.poll_once()
        assert not any("@cass:" in c for _, _, c in rec.messages)

    async def test_dms_and_remember_false_keep_nothing_heard(self, make_organ, babelr):
        rec = _Recorder()
        organ = make_organ(recorder=rec)
        organ.start()
        await organ.poll_once()
        organ.config.terms_path.write_text(json.dumps({"remember": False}))
        babelr.say("general", KOHL, "just chatting")
        await organ.poll_once()
        assert rec.messages == []


    async def test_a_dm_request_isnt_heard(self, make_organ, babelr):
        rec = _Recorder()
        organ = make_organ(recorder=rec)
        organ.start()
        await organ.poll_once()
        organ._record_heard(type("E", (), {"kind": "dm_request", "author_name": "robokohl",
                                           "text": None, "place": "dm:x", "place_label": "DM request"})())
        assert rec.messages == [] and rec.created == []


# -- house attention (her yes, 2026-11-24) --------------------------------------------

class TestAttend:
    def _organ(self, make_organ, reply, attend=True):
        organ = make_organ(reply=reply, attend_from="kohl")
        if attend:
            organ.config.terms_path.parent.mkdir(parents=True, exist_ok=True)
            organ.config.terms_path.write_text(json.dumps({"attend": True}))
        organ.start()
        return organ

    async def test_an_unmentioned_kohl_post_offers_her_a_turn(self, make_organ, babelr):
        organ = self._organ(make_organ, "Something specific.")
        await organ.poll_once()
        babelr.say("general", KOHL, "/attend on")
        await organ.poll_once()
        babelr.say("general", KOHL, "crazy day, huh")
        await organ.poll_once()
        assert len(organ.wakes) == 1
        events, context = organ.wakes[0]
        assert context["offered"] and "offered a turn" in context["prompt"]
        assert babelr.agents[-1].sent[-1] == ("channel", "chan-general", "Something specific.")

    async def test_pass_posts_nothing(self, make_organ, babelr):
        organ = self._organ(make_organ, "PASS")
        await organ.poll_once()
        babelr.say("general", KOHL, "/attend on")
        babelr.say("general", KOHL, "anyone?")
        await organ.poll_once()
        assert len(organ.wakes) == 1
        assert not any(s[0] == "channel" for s in babelr.agents[-1].sent)

    async def test_no_offer_without_her_term_attention_or_from_others(self, make_organ, babelr):
        organ = self._organ(make_organ, "x", attend=False)
        await organ.poll_once()
        babelr.say("general", KOHL, "/attend on")
        babelr.say("general", KOHL, "crazy day")
        await organ.poll_once()
        assert organ.wakes == [], "her terms don't say attend"

        organ.config.terms_path.write_text(json.dumps({"attend": True}))
        babelr.say("general", ROBOKOHL, "an agent's post")
        babelr.say("general", KOHL, "@robokohl just you")
        await organ.poll_once()
        assert organ.wakes == [], "only Kohl's posts that name nobody"

        babelr.say("general", KOHL, "/attend off")
        babelr.say("general", KOHL, "quiet now")
        await organ.poll_once()
        assert organ.wakes == []

    async def test_attention_turned_on_before_she_started_is_caught_up(self, make_organ, babelr):
        babelr.say("general", KOHL, "/attend on")   # before she's present
        organ = self._organ(make_organ, "Here.")
        await organ.poll_once()                      # first sight: history, and the catch-up
        babelr.say("general", KOHL, "crazy day")
        await organ.poll_once()
        assert len(organ.wakes) == 1 and organ.wakes[0][1]["offered"]


class TestRestartContext:
    async def test_after_a_restart_her_first_turn_has_the_room(self, make_organ, babelr):
        organ = make_organ(reply="hi")
        organ.start()
        await organ.poll_once()
        babelr.say("general", KOHL, "earlier thing")
        await organ.poll_once()
        reborn = make_organ(reply="hi")   # a restart: same state, empty buffers
        reborn.start()
        babelr.say("general", ROBOKOHL, "@cass you there?")
        await reborn.poll_once()
        events, context = reborn.wakes[-1]
        assert "@kohl: earlier thing" in context["recent"]
        assert [e.text for e in events] == ["@cass you there?"]


class TestReactions:
    """Kohl, 2026-11-24: "maybe integrate message reacts?" She sees reactions,
    sees which of hers landed, and can react herself."""

    async def test_read_shows_ids_and_reactions_by_name(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        await organ.poll_once()
        msg = babelr.say("general", KOHL, "look at this bagel")
        await organ.poll_once()
        babelr.react(msg["id"], KOHL, "🥯")
        await organ.poll_once()  # a reaction on something already seen updates it
        got = organ.read("general")["messages"][-1]
        assert got["id"] == msg["id"] and got["reactions"] == {"🥯": ["kohl"]}

    async def test_reactions_to_what_she_said(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        await organ.poll_once()
        babelr.say("general", KOHL, "tell me a joke")  # she knows Kohl by name from here
        await organ.poll_once()
        sent = organ.post("general", "a pun about tides")
        babelr.react(sent["message_id"], KOHL, "😂")
        await organ.poll_once()
        mine = organ.read("general")["reactions_to_you"]
        assert mine == [{"you_said": "a pun about tides", "published": mine[0]["published"],
                         "reactions": {"😂": ["kohl"]}}]

    async def test_her_own_reaction_is_not_feedback(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        await organ.poll_once()
        sent = organ.post("general", "hello")
        assert organ.react("general", sent["message_id"], "👋")["success"]
        await organ.poll_once()
        assert "reactions_to_you" not in organ.read("general")

    async def test_react_and_take_it_back(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        await organ.poll_once()
        msg = babelr.say("general", KOHL, "good morning")
        await organ.poll_once()
        assert organ.react("general", msg["id"], "☀️")["success"]
        assert babelr.reactions[msg["id"]] == {"☀️": [CASS["id"]]}
        assert organ.react("general", msg["id"], "☀️", remove=True)["success"]
        assert babelr.reactions[msg["id"]] == {"☀️": []}
        assert not organ.react("nowhere", msg["id"], "☀️")["success"]

    async def test_dm_reactions(self, make_organ, babelr):
        organ = make_organ()
        organ.start()
        await organ.poll_once()
        babelr.dm_from(KOHL, "here's a meme")
        await organ.poll_once()
        assert organ.react("kohl", organ.read("kohl")["messages"][-1]["id"], "😂")["success"]
