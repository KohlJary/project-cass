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
        # Only what reached her (and her reply) lands in her history.
        assert [c for _, _, c in recorder.messages] == [
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
