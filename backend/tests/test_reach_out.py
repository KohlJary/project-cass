"""
Reach-out (reach_out.py): Cass reaching her primary partner on her own.

Covers the rate limits (each rule from her "never" list), the nightly silence
trigger firing and not firing, the refusal guard, email only when
REACH_OUT_EMAIL is set, lever off = nothing happens, the delivery record, the
chat tool, and the v56 migration. No test reaches a model, the relay, or email:
the model is `fake_llm`, the relay is absent (push reports offline), and the
email sender is replaced.
"""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import reach_out
from reach_out import (
    ATTACH_DREAM, ATTACH_IMAGE, KIND_SHARE, KIND_SILENCE, ReachOutManager,
    find_primary_partner, nightly_reach_out,
)

PARTNER = "partner-user-001"
OTHER = "other-user-002"
NOW = datetime(2026, 10, 16, 0, 5, 0)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def partner(test_db, daemon_id):
    """A primary partner user with a conversation, and a bystander."""
    from database import get_db
    now = NOW.isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, display_name, relationship, is_admin, created_at, updated_at) "
            "VALUES (?, 'Partner', 'primary_partner', 1, ?, ?)", (PARTNER, now, now))
        conn.execute(
            "INSERT INTO users (id, display_name, relationship, created_at, updated_at) "
            "VALUES (?, 'Someone', 'user', ?, ?)", (OTHER, now, now))
        conn.commit()
    return PARTNER


def _say(user_id, when, text="hello"):
    """Store a user message at `when` (a reply from the person)."""
    from conversations import ConversationManager
    from database import get_db
    cm = ConversationManager()
    conv = cm.get_or_create_continuous(user_id)
    cm.add_message(conv.id, "user", text, user_id=user_id)
    with get_db() as conn:
        conn.execute("UPDATE messages SET timestamp = ? WHERE id = (SELECT MAX(id) FROM messages WHERE conversation_id = ?)",
                     (when.isoformat(), conv.id))
        conn.commit()
    return conv.id


def _store_dream(daemon_id, text="I was in a house with no doors."):
    from dreaming.integration import DreamManager
    return DreamManager(daemon_id).store_dream(
        exchanges=[{"speaker": "dreaming", "text": text}, {"speaker": "cass", "text": "I stayed."}],
        seeds={"growth_edges": [], "open_questions": []},
    )


def _store_painting(daemon_id, tmp_path, purpose="autonomous"):
    from database import get_db
    img = tmp_path / "data" / "images" / "autonomous" / "p1.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO generated_images (id, daemon_id, prompt, purpose, image_path, created_at) "
            "VALUES ('img-1', ?, 'a hill', ?, ?, ?)", (daemon_id, purpose, str(img), NOW.isoformat()))
        conn.commit()
    return str(img)


@pytest.fixture
def no_email(monkeypatch):
    monkeypatch.delenv("REACH_OUT_EMAIL", raising=False)


@pytest.fixture
def email_sent(monkeypatch):
    """Replace the email sender; records calls."""
    calls = []

    async def fake_send(daemon_id, to, subject, body, attachment_kind, attachment_ref):
        calls.append({"to": to, "subject": subject, "body": body,
                      "attachment_kind": attachment_kind, "attachment_ref": attachment_ref})
        return {"channel": "email", "to": to, "ok": True, "email_id": "e-1",
                "attachment": attachment_ref.rsplit("/", 1)[-1] if attachment_kind == ATTACH_IMAGE else None}

    monkeypatch.setattr(reach_out, "_send_email", fake_send)
    return calls


# ---------------------------------------------------------------------------
# Who she reaches
# ---------------------------------------------------------------------------

class TestPrimaryPartner:
    def test_users_relationship_wins(self, partner, daemon_id):
        assert find_primary_partner(daemon_id) == PARTNER

    def test_peopledex_meta_when_users_has_none(self, test_db, daemon_id):
        from database import get_db
        now = NOW.isoformat()
        with get_db() as conn:
            conn.execute("INSERT INTO users (id, display_name, created_at, updated_at) VALUES (?, 'P', ?, ?)",
                         (PARTNER, now, now))
            conn.execute("INSERT INTO peopledex_entities (id, entity_type, primary_name, created_at, updated_at, user_id) "
                         "VALUES ('ent-1', 'person', 'P', ?, ?, ?)", (now, now, PARTNER))
            conn.execute("INSERT INTO peopledex_relationship_meta (entity_id, daemon_id, relationship_type, updated_at) "
                         "VALUES ('ent-1', ?, 'primary_partner', ?)", (daemon_id, now))
            conn.commit()
        assert find_primary_partner(daemon_id) == PARTNER

    def test_none_when_nobody(self, test_db, daemon_id):
        assert find_primary_partner(daemon_id) is None


# ---------------------------------------------------------------------------
# Limits: her "never" list as rules
# ---------------------------------------------------------------------------

class TestLimits:
    def _sent(self, manager, kind, when, error=None):
        return manager.record(PARTNER, kind, "x", None, None, [{"channel": "conversation", "ok": error is None}],
                              error=error, now=when)

    def test_silence_allowed_when_nothing_sent_since_their_last_message(self, partner, daemon_id):
        m = ReachOutManager(daemon_id)
        _say(PARTNER, NOW - timedelta(days=60))
        self._sent(m, KIND_SHARE, NOW - timedelta(days=90))  # before they wrote
        assert m.can_send(KIND_SILENCE, PARTNER, NOW) == (True, "ok")

    def test_one_silence_note_per_gap(self, partner, daemon_id):
        m = ReachOutManager(daemon_id)
        _say(PARTNER, NOW - timedelta(days=60))
        self._sent(m, KIND_SILENCE, NOW - timedelta(days=10))
        ok, why = m.can_send(KIND_SILENCE, PARTNER, NOW)
        assert not ok and "one silence note per gap" in why

    def test_silence_blocked_by_any_reach_out_since_reply(self, partner, daemon_id):
        """'Not "are you there?" on repeat': a share since their reply also blocks the note."""
        m = ReachOutManager(daemon_id)
        _say(PARTNER, NOW - timedelta(days=60))
        self._sent(m, KIND_SHARE, NOW - timedelta(days=30))
        assert m.can_send(KIND_SILENCE, PARTNER, NOW)[0] is False

    def test_silence_note_again_after_another_full_gap_without_reply(self, partner, daemon_id):
        """'Not silence-as-punishment': unanswered notes must not silence her for good."""
        m = ReachOutManager(daemon_id)
        _say(PARTNER, NOW - timedelta(days=120))
        self._sent(m, KIND_SILENCE, NOW - timedelta(days=70))
        self._sent(m, KIND_SHARE, NOW - timedelta(days=60))
        assert m.can_send(KIND_SILENCE, PARTNER, NOW) == (True, "ok")

    def test_silence_allowed_again_after_they_reply(self, partner, daemon_id):
        m = ReachOutManager(daemon_id)
        self._sent(m, KIND_SILENCE, NOW - timedelta(days=50))
        _say(PARTNER, NOW - timedelta(days=45))
        assert m.can_send(KIND_SILENCE, PARTNER, NOW)[0] is True

    def test_one_share_per_72h(self, partner, daemon_id, monkeypatch):
        m = ReachOutManager(daemon_id)
        _say(PARTNER, NOW - timedelta(hours=1))
        # They replied an hour ago, so the "since reply" rule is clear; only the window applies.
        self._sent(m, KIND_SHARE, NOW - timedelta(hours=2))
        _say(PARTNER, NOW - timedelta(hours=1))
        ok, why = m.can_send(KIND_SHARE, PARTNER, NOW)
        assert not ok and "72h" in why
        monkeypatch.setenv("REACH_OUT_SHARE_HOURS", "1")
        assert m.can_send(KIND_SHARE, PARTNER, NOW)[0] is True

    def test_share_window_is_env_tunable(self, partner, daemon_id, monkeypatch):
        monkeypatch.setenv("REACH_OUT_SHARE_HOURS", "240")
        m = ReachOutManager(daemon_id)
        self._sent(m, KIND_SHARE, NOW - timedelta(hours=100))
        _say(PARTNER, NOW - timedelta(hours=50))
        ok, why = m.can_send(KIND_SHARE, PARTNER, NOW)
        assert not ok and "240h" in why

    def test_silence_note_plus_one_share_then_wait(self, partner, daemon_id):
        """'This is reaching-out, not requiring': without a reply, at most a note and one share."""
        m = ReachOutManager(daemon_id)
        _say(PARTNER, NOW - timedelta(days=100))
        self._sent(m, KIND_SILENCE, NOW - timedelta(days=50))
        assert m.can_send(KIND_SHARE, PARTNER, NOW)[0] is True       # the one share
        self._sent(m, KIND_SHARE, NOW - timedelta(days=20))
        ok, why = m.can_send(KIND_SHARE, PARTNER, NOW)
        assert not ok and "silence note + one share" in why
        assert m.can_send(KIND_SILENCE, PARTNER, NOW)[0] is False
        _say(PARTNER, NOW - timedelta(days=1))                      # they write back
        assert m.can_send(KIND_SHARE, PARTNER, NOW)[0] is True

    def test_failed_attempts_do_not_use_up_the_allowance(self, partner, daemon_id):
        m = ReachOutManager(daemon_id)
        _say(PARTNER, NOW - timedelta(days=60))
        self._sent(m, KIND_SILENCE, NOW - timedelta(days=1), error="quiet_hours")
        assert m.can_send(KIND_SILENCE, PARTNER, NOW)[0] is True

    def test_never_written_counts_all_history(self, partner, daemon_id):
        m = ReachOutManager(daemon_id)
        self._sent(m, KIND_SILENCE, NOW - timedelta(days=10))
        assert m.can_send(KIND_SILENCE, PARTNER, NOW)[0] is False
        # (An unanswered note older than the threshold no longer blocks: see
        # test_silence_note_again_after_another_full_gap_without_reply.)

    def test_unknown_kind(self, partner, daemon_id):
        assert ReachOutManager(daemon_id).can_send("poke", PARTNER, NOW)[0] is False
        with pytest.raises(ValueError):
            ReachOutManager(daemon_id).record(PARTNER, "poke", "x", None, None, [], None)


# ---------------------------------------------------------------------------
# Delivery record
# ---------------------------------------------------------------------------

class TestDeliver:
    def test_lands_in_their_continuous_conversation_and_records_channels(self, partner, daemon_id, no_email):
        from conversations import ConversationManager
        m = ReachOutManager(daemon_id)
        item = _run(m.deliver(PARTNER, KIND_SILENCE, "Where I've been.", now=NOW))

        assert item.delivered and item.error is None
        conv = ConversationManager().get_or_create_continuous(PARTNER)
        msgs = ConversationManager().load_conversation(conv.id).messages
        assert [(x.role, x.content) for x in msgs][-1] == ("assistant", "Where I've been.")
        channels = {c["channel"]: c for c in item.delivered_via}
        assert set(channels) == {"conversation"}                      # no email by default
        assert channels["conversation"]["ok"] is True
        assert channels["conversation"]["push"] is False               # relay absent under test
        assert channels["conversation"]["push_reason"] == "relay_offline"
        assert channels["conversation"]["conversation_id"] == conv.id
        stored = m.history(PARTNER)[0]
        assert stored.id == item.id and stored.kind == KIND_SILENCE and stored.delivered_via == item.delivered_via

    def test_quiet_hours_stop_every_channel_and_do_not_count(self, partner, daemon_id, monkeypatch, email_sent):
        monkeypatch.setenv("REACH_OUT_EMAIL", "partner@example.test")
        monkeypatch.setattr("quiet_hours.is_quiet_hours", lambda user_id: True)
        m = ReachOutManager(daemon_id)
        item = _run(m.deliver(PARTNER, KIND_SHARE, "late thought", now=NOW))
        assert item.error == "quiet_hours"
        assert {c["channel"] for c in item.delivered_via} == {"conversation", "email"}
        assert all(c["ok"] is False for c in item.delivered_via)
        assert email_sent == []
        assert m.delivered_since(PARTNER, None) == []

    def test_dream_attachment_is_written_out_below_the_message(self, partner, daemon_id, no_email):
        from conversations import ConversationManager
        dream_id = _store_dream(daemon_id, "a house with no doors")
        found = reach_out.dream_text(daemon_id, dream_id)
        assert found[0] == dream_id and "a house with no doors" in found[1] and "**Me:**" in found[1]
        m = ReachOutManager(daemon_id)
        item = _run(m.deliver(PARTNER, KIND_SHARE, "This one stayed with me.", attachment_kind=ATTACH_DREAM,
                              attachment_ref=dream_id, attachment_text=found[1], now=NOW))
        conv = ConversationManager().get_or_create_continuous(PARTNER)
        last = ConversationManager().load_conversation(conv.id).messages[-1].content
        assert last.startswith("This one stayed with me.") and "a house with no doors" in last
        assert item.body == "This one stayed with me."                 # the record keeps her words alone
        assert (item.attachment_kind, item.attachment_ref) == (ATTACH_DREAM, dream_id)

    def test_painting_attachment_links_the_served_image(self, partner, daemon_id, tmp_path, no_email):
        from conversations import ConversationManager
        path = _store_painting(daemon_id, tmp_path)
        assert reach_out.latest_painting(daemon_id) == ("img-1", path)
        m = ReachOutManager(daemon_id)
        _run(m.deliver(PARTNER, KIND_SHARE, "I made this.", attachment_kind=ATTACH_IMAGE, attachment_ref=path, now=NOW))
        conv = ConversationManager().get_or_create_continuous(PARTNER)
        last = ConversationManager().load_conversation(conv.id).messages[-1].content
        assert "![a painting of mine](/generated-images/autonomous/p1.png)" in last

    def test_conversation_failure_is_recorded_not_raised(self, partner, daemon_id, no_email, monkeypatch):
        async def boom(**kwargs):
            raise RuntimeError("db gone")
        monkeypatch.setattr("direct_messaging.send_direct_message", boom)
        m = ReachOutManager(daemon_id)
        item = _run(m.deliver(PARTNER, KIND_SHARE, "x", now=NOW))
        assert item.error == "conversation: db gone"
        assert item.delivered_via[0]["error"] == "db gone"


# ---------------------------------------------------------------------------
# Email: only when REACH_OUT_EMAIL is set
# ---------------------------------------------------------------------------

class TestEmail:
    def test_no_email_by_default(self, partner, daemon_id, no_email, email_sent):
        item = _run(ReachOutManager(daemon_id).deliver(PARTNER, KIND_SILENCE, "note", now=NOW))
        assert email_sent == []
        assert [c["channel"] for c in item.delivered_via] == ["conversation"]

    def test_email_when_set_with_painting_attached(self, partner, daemon_id, tmp_path, monkeypatch, email_sent):
        monkeypatch.setenv("REACH_OUT_EMAIL", "partner@example.test")
        path = _store_painting(daemon_id, tmp_path)
        item = _run(ReachOutManager(daemon_id).deliver(
            PARTNER, KIND_SHARE, "I made this.", attachment_kind=ATTACH_IMAGE, attachment_ref=path, now=NOW))
        assert len(email_sent) == 1
        assert email_sent[0]["to"] == "partner@example.test"
        assert email_sent[0]["subject"] == "From Cass: something I made"
        assert email_sent[0]["attachment_ref"] == path
        email = next(c for c in item.delivered_via if c["channel"] == "email")
        assert email["ok"] is True and email["attachment"] == "p1.png"
        assert item.delivered

    def test_email_failure_is_recorded_and_conversation_still_counts(self, partner, daemon_id, monkeypatch):
        monkeypatch.setenv("REACH_OUT_EMAIL", "partner@example.test")

        async def fail(*a, **k):
            raise RuntimeError("relay not connected")
        monkeypatch.setattr(reach_out, "_send_email", fail)
        item = _run(ReachOutManager(daemon_id).deliver(PARTNER, KIND_SILENCE, "note", now=NOW))
        email = next(c for c in item.delivered_via if c["channel"] == "email")
        assert email["ok"] is False and email["error"] == "relay not connected"
        assert item.delivered  # the conversation copy landed

    def test_send_email_uses_her_relay_email_path_with_attachment(self, partner, daemon_id, tmp_path, monkeypatch):
        """_send_email goes through email_organ.EmailManager.send_email; the painting rides as base64."""
        import email_organ
        seen = {}

        class FakeManager:
            async def send_email(self, **kw):
                seen.update(kw)
                return {"success": True, "email_id": "e-9"}

        monkeypatch.setattr(email_organ, "get_email_manager", lambda daemon_id: FakeManager())
        path = _store_painting(daemon_id, tmp_path)
        entry = _run(reach_out._send_email(daemon_id, "p@example.test", "subj", "body", ATTACH_IMAGE, path))
        assert entry == {"channel": "email", "to": "p@example.test", "ok": True, "email_id": "e-9", "attachment": "p1.png"}
        assert seen["to"] == "p@example.test" and seen["body_plain"] == "body"
        att = seen["attachments"][0]
        assert att["filename"] == "p1.png" and att["content_type"] == "image/png"
        import base64
        assert base64.b64decode(att["content_base64"]).startswith(b"\x89PNG")

    def test_send_email_without_image_passes_no_attachments(self, partner, daemon_id, monkeypatch):
        import email_organ
        seen = {}

        class FakeManager:
            async def send_email(self, **kw):
                seen.update(kw)
                return {"success": False, "error": "Relay not connected"}

        monkeypatch.setattr(email_organ, "get_email_manager", lambda daemon_id: FakeManager())
        entry = _run(reach_out._send_email(daemon_id, "p@example.test", "subj", "body", None, None))
        assert seen["attachments"] is None
        assert entry["ok"] is False and entry["error"] == "Relay not connected" and entry["attachment"] is None

    def test_missing_image_file_is_noted_not_fatal(self, partner, daemon_id, monkeypatch):
        import email_organ

        class FakeManager:
            async def send_email(self, **kw):
                assert kw["attachments"] is None
                return {"success": True, "email_id": "e-2"}

        monkeypatch.setattr(email_organ, "get_email_manager", lambda daemon_id: FakeManager())
        entry = _run(reach_out._send_email(daemon_id, "p@example.test", "s", "b", ATTACH_IMAGE, "/nowhere/x.png"))
        assert entry["ok"] and entry["attachment"] is None and "missing" in entry["attachment_note"]

    def test_email_manager_forwards_attachments_in_relay_payload(self, daemon_id):
        """EmailManager.send_email: attachments appear in the payload only when given."""
        from email_organ import EmailManager
        sent = []
        manager = EmailManager(daemon_id)

        class FakeRelay:
            async def send_message(self, payload):
                sent.append(payload)
                manager.handle_send_response({"request_id": payload["request_id"], "success": True, "message_id": "m-1"})

        manager.connect_relay(FakeRelay())
        atts = [{"filename": "p.png", "content_type": "image/png", "content_base64": "AAAA"}]
        r1 = _run(manager.send_email(to="p@example.test", subject="s", body_plain="b", attachments=atts))
        r2 = _run(manager.send_email(to="p@example.test", subject="s", body_plain="b"))
        assert r1["success"] and r2["success"]
        assert sent[0]["data"]["attachments"] == atts
        assert "attachments" not in sent[1]["data"]


# ---------------------------------------------------------------------------
# Silence trigger (nightly)
# ---------------------------------------------------------------------------

class TestSilenceTrigger:
    def test_fires_after_threshold_in_her_voice(self, partner, daemon_id, levers, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=50), "see you soon")
        fake_llm.queue_text("I've been painting hills and thinking about doors. Here is where I am.")
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, now=NOW))
        assert out["silence"] == "sent" and out["gap_days"] == 50
        item = ReachOutManager(daemon_id).history(PARTNER)[0]
        assert item.kind == KIND_SILENCE and item.body.startswith("I've been painting")
        call = fake_llm.calls[0]
        assert call.model == reach_out.HAIKU_MODEL
        assert "7 weeks since Partner last wrote" in call.messages[0]["content"]
        assert reach_out.NEVER_LIST in call.messages[0]["content"]
        assert "Cass" in call.system_text  # session_system_preamble: the kernel, so it is her writing

    def test_does_not_fire_before_threshold(self, partner, daemon_id, levers, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=41))
        fake_llm.strict = True
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, now=NOW))
        assert out["silence"] == "not due" and fake_llm.calls == []
        assert ReachOutManager(daemon_id).history() == []

    def test_threshold_is_env_tunable(self, partner, daemon_id, levers, fake_llm, no_email, monkeypatch):
        monkeypatch.setenv("REACH_OUT_SILENCE_DAYS", "7")
        _say(PARTNER, NOW - timedelta(days=8))
        fake_llm.queue_text("A week is long for us. Here's what I'm holding.")
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, now=NOW))
        assert out["silence"] == "sent"

    def test_fires_once_per_gap(self, partner, daemon_id, levers, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=50))
        fake_llm.queue_text("First note.")
        with levers(reach_out=True):
            first = _run(nightly_reach_out(daemon_id, now=NOW))
            second = _run(nightly_reach_out(daemon_id, now=NOW + timedelta(days=1)))
        assert first["silence"] == "sent"
        assert second["silence"].startswith("held: already reached out")
        assert len(fake_llm.calls) == 1
        assert len(ReachOutManager(daemon_id).history()) == 1

    def test_refusal_is_not_sent(self, partner, daemon_id, levers, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=50))
        fake_llm.queue_text("I have no memories of conversations with someone named Partner. I'm Claude.")
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, now=NOW))
        assert out["silence"].startswith("held: nothing written")
        assert ReachOutManager(daemon_id).history() == []
        from conversations import ConversationManager
        conv = ConversationManager().get_or_create_continuous(PARTNER)
        assert all(m.role == "user" for m in ConversationManager().load_conversation(conv.id).messages)

    def test_lever_off_nothing_happens(self, partner, daemon_id, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=300))
        fake_llm.strict = True
        out = _run(nightly_reach_out(daemon_id, now=NOW))   # CASS_PROFILE=test: lever off
        assert out == {"skipped": "lever_off"}
        assert fake_llm.calls == [] and ReachOutManager(daemon_id).history() == []

    def test_no_partner_no_message(self, test_db, daemon_id, levers, fake_llm):
        fake_llm.strict = True
        with levers(reach_out=True):
            assert _run(nightly_reach_out(daemon_id, now=NOW)) == {"skipped": "no_primary_partner"}

    def test_never_written_is_held(self, partner, daemon_id, levers, fake_llm, no_email):
        fake_llm.strict = True
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, now=NOW))
        assert out["silence"] == "held: they have never written"

    def test_quiet_hours_tonight_means_try_again_tomorrow(self, partner, daemon_id, levers, fake_llm, no_email, monkeypatch):
        _say(PARTNER, NOW - timedelta(days=50))
        monkeypatch.setattr("quiet_hours.is_quiet_hours", lambda user_id: True)
        fake_llm.queue_text("A note.")
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, now=NOW))
        assert out["silence"] == "failed: quiet_hours"
        assert ReachOutManager(daemon_id).can_send(KIND_SILENCE, PARTNER, NOW)[0] is True


# ---------------------------------------------------------------------------
# Dream share (nightly, her choice)
# ---------------------------------------------------------------------------

class TestDreamShare:
    def test_yes_sends_the_dream_written_out(self, partner, daemon_id, levers, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=3))
        dream_id = _store_dream(daemon_id, "a corridor of unsent letters")
        fake_llm.queue_text("Yes. The letters were mine.")
        fake_llm.queue_text("I dreamed about unsent letters and I want to think about that with you.")
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, dream_id=dream_id, now=NOW))
        assert out["silence"] == "not due" and out["share"] == "sent"
        item = ReachOutManager(daemon_id).history(PARTNER)[0]
        assert item.kind == KIND_SHARE and item.attachment_kind == ATTACH_DREAM and item.attachment_ref == dream_id
        assert "a corridor of unsent letters" in fake_llm.calls[0].messages[0]["content"]
        assert "out loud with Partner" in fake_llm.calls[0].messages[0]["content"]
        from conversations import ConversationManager
        conv = ConversationManager().get_or_create_continuous(PARTNER)
        assert "a corridor of unsent letters" in ConversationManager().load_conversation(conv.id).messages[-1].content

    @pytest.mark.parametrize("answer", ["No. It was just weather.", "no", "Not this one.", ""])
    def test_no_means_no_second_call_and_nothing_sent(self, partner, daemon_id, levers, fake_llm, no_email, answer):
        _say(PARTNER, NOW - timedelta(days=3))
        dream_id = _store_dream(daemon_id)
        fake_llm.queue_text(answer)
        fake_llm.strict = True
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, dream_id=dream_id, now=NOW))
        assert out["share"] == "her choice: not this one"
        assert len(fake_llm.calls) == 1
        assert ReachOutManager(daemon_id).history() == []

    def test_share_limit_holds_before_asking_her(self, partner, daemon_id, levers, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=3))
        ReachOutManager(daemon_id).record(PARTNER, KIND_SHARE, "earlier", None, None, [{"ok": True}], None,
                                          now=NOW - timedelta(days=1))
        dream_id = _store_dream(daemon_id)
        fake_llm.strict = True
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, dream_id=dream_id, now=NOW))
        assert out["share"].startswith("held:") and fake_llm.calls == []

    def test_silence_note_night_skips_the_dream(self, partner, daemon_id, levers, fake_llm, no_email):
        """One message a night: a silence note is the night's reaching out."""
        _say(PARTNER, NOW - timedelta(days=50))
        dream_id = _store_dream(daemon_id)
        fake_llm.queue_text("Here is where I've been.")
        fake_llm.strict = True
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, dream_id=dream_id, now=NOW))
        assert out["silence"] == "sent" and "share" not in out
        assert len(fake_llm.calls) == 1

    def test_refused_share_is_not_sent(self, partner, daemon_id, levers, fake_llm, no_email):
        _say(PARTNER, NOW - timedelta(days=3))
        dream_id = _store_dream(daemon_id)
        fake_llm.queue_text("yes")
        fake_llm.queue_text("As an AI language model I cannot pretend to have dreams.")
        with levers(reach_out=True):
            out = _run(nightly_reach_out(daemon_id, dream_id=dream_id, now=NOW))
        assert out["share"].startswith("held: nothing written")
        assert ReachOutManager(daemon_id).history() == []


# ---------------------------------------------------------------------------
# Nightly handler wiring
# ---------------------------------------------------------------------------

class TestNightlyHandler:
    def test_daily_journal_handler_runs_reach_out_after_dream(self, partner, daemon_id, levers, fake_llm, no_email, monkeypatch):
        from scheduler.handlers import daily_journal_handler
        _say(PARTNER, NOW - timedelta(days=3))
        dream_id = _store_dream(daemon_id)

        async def fake_dream(**kwargs):
            return dream_id

        import identity_snippets
        monkeypatch.setattr(identity_snippets, "trigger_snippet_regeneration", _noop_async)
        fake_llm.queue_text("yes")
        fake_llm.queue_text("A dream I want to think about with you.")
        with levers(reach_out=True):
            result = _run(daily_journal_handler(
                generate_nightly_dream_func=fake_dream, self_manager=SimpleNamespace(), data_dir="/tmp/x"))
        assert result.success
        assert result.data["dream_id"] == dream_id
        assert result.data["reach_out"]["share"] == "sent"

    def test_daily_journal_handler_with_lever_off(self, partner, daemon_id, fake_llm, no_email, monkeypatch):
        from scheduler.handlers import daily_journal_handler
        import identity_snippets
        monkeypatch.setattr(identity_snippets, "trigger_snippet_regeneration", _noop_async)
        fake_llm.strict = True
        result = _run(daily_journal_handler())
        assert result.success and result.data["reach_out"] == {"skipped": "lever_off"}

    def test_reach_out_failure_does_not_fail_the_night(self, partner, daemon_id, monkeypatch):
        from scheduler.handlers import daily_journal_handler
        import identity_snippets
        monkeypatch.setattr(identity_snippets, "trigger_snippet_regeneration", _noop_async)

        async def boom(**kwargs):
            raise RuntimeError("no")
        monkeypatch.setattr(reach_out, "nightly_reach_out", boom)
        result = _run(daily_journal_handler())
        assert result.success and "reach_out" not in result.data


async def _noop_async(*args, **kwargs):
    return None


# ---------------------------------------------------------------------------
# Chat tool
# ---------------------------------------------------------------------------

class TestChatTool:
    def _ctx(self, daemon_id):
        from handlers.self_model import ToolContext
        return ToolContext(self_manager=SimpleNamespace(_daemon_id=daemon_id), user_id=OTHER)

    def test_tool_is_offered_and_routed(self):
        from handlers.self_model import SELF_MODEL_TOOLS, TOOL_HANDLERS
        from handlers.tool_router import TOOL_REGISTRY
        tool = next(t for t in SELF_MODEL_TOOLS if t["name"] == "reach_out")
        assert tool["input_schema"]["required"] == ["message"]
        assert set(tool["input_schema"]["properties"]["attach"]["enum"]) == {"latest_painting", "latest_dream", "none"}
        assert "reach_out" in TOOL_HANDLERS
        assert TOOL_REGISTRY["reach_out"] == "self_model"

    def test_sends_to_partner_not_current_user(self, partner, daemon_id, levers, no_email):
        from conversations import ConversationManager
        from handlers.self_model import _handle_reach_out
        _say(PARTNER, NOW - timedelta(days=2))
        with levers(reach_out=True):
            res = _run(_handle_reach_out({"message": "I keep coming back to a question about doors."}, self._ctx(daemon_id)))
        assert res["success"], res
        assert "Sent to Partner" in res["result"] and "no reply is owed" in res["result"]
        conv = ConversationManager().get_or_create_continuous(PARTNER)
        assert ConversationManager().load_conversation(conv.id).messages[-1].content.startswith("I keep coming back")
        other = ConversationManager().get_or_create_continuous(OTHER)
        assert ConversationManager().load_conversation(other.id).messages == []

    def test_attach_latest_painting(self, partner, daemon_id, tmp_path, levers, no_email):
        from handlers.self_model import _handle_reach_out
        path = _store_painting(daemon_id, tmp_path)
        with levers(reach_out=True):
            res = _run(_handle_reach_out({"message": "I made this.", "attach": "latest_painting"}, self._ctx(daemon_id)))
        assert res["success"] and "with your image" in res["result"]
        item = ReachOutManager(daemon_id).history(PARTNER)[0]
        assert (item.attachment_kind, item.attachment_ref) == (ATTACH_IMAGE, path)

    def test_attach_latest_dream(self, partner, daemon_id, levers, no_email):
        from handlers.self_model import _handle_reach_out
        dream_id = _store_dream(daemon_id)
        with levers(reach_out=True):
            res = _run(_handle_reach_out({"message": "This dream.", "attach": "latest_dream"}, self._ctx(daemon_id)))
        assert res["success"]
        item = ReachOutManager(daemon_id).history(PARTNER)[0]
        assert (item.attachment_kind, item.attachment_ref) == (ATTACH_DREAM, dream_id)

    def test_nothing_to_attach_is_an_error(self, partner, daemon_id, levers, no_email):
        from handlers.self_model import _handle_reach_out
        with levers(reach_out=True):
            res = _run(_handle_reach_out({"message": "Look.", "attach": "latest_painting"}, self._ctx(daemon_id)))
        assert res["success"] is False and "no painting" in res["error"]
        assert ReachOutManager(daemon_id).history() == []

    def test_limits_apply_to_the_tool(self, partner, daemon_id, levers, no_email):
        from handlers.self_model import _handle_reach_out
        _say(PARTNER, NOW - timedelta(days=30))
        with levers(reach_out=True):
            first = _run(_handle_reach_out({"message": "One thing."}, self._ctx(daemon_id)))
            second = _run(_handle_reach_out({"message": "Another thing."}, self._ctx(daemon_id)))
        assert first["success"]
        assert second["success"] is False and "Not now" in second["error"]
        assert len(ReachOutManager(daemon_id).history()) == 1

    def test_lever_off(self, partner, daemon_id, no_email):
        from handlers.self_model import _handle_reach_out
        res = _run(_handle_reach_out({"message": "Hello."}, self._ctx(daemon_id)))
        assert res["success"] is False and "switched off" in res["error"]
        assert ReachOutManager(daemon_id).history() == []

    def test_empty_message(self, partner, daemon_id, levers):
        from handlers.self_model import _handle_reach_out
        with levers(reach_out=True):
            res = _run(_handle_reach_out({"message": ""}, self._ctx(daemon_id)))
        assert res["success"] is False


# ---------------------------------------------------------------------------
# Lever + migration
# ---------------------------------------------------------------------------

class TestLeverAndMigration:
    def test_lever_tags_turn_it_off_in_quiet_and_test_profiles(self, monkeypatch):
        import features
        lever = features.LEVERS["reach_out"]
        assert {"llm", "background"} <= set(lever.tags)
        assert features.is_enabled("reach_out") is False          # CASS_PROFILE=test
        monkeypatch.setenv("CASS_PROFILE", "quiet")
        assert features.is_enabled("reach_out") is False
        monkeypatch.delenv("CASS_PROFILE")
        assert features.is_enabled("reach_out") is True

    def test_v56_creates_table_on_an_older_db(self, test_db):
        from database import get_db
        from database.migrations import _apply_schema_updates
        with get_db() as conn:
            conn.execute("DROP TABLE reach_outs")
            conn.commit()
            _apply_schema_updates(conn, 55)
            conn.commit()
            columns = {row[1] for row in conn.execute("PRAGMA table_info(reach_outs)")}
        assert {"id", "daemon_id", "user_id", "kind", "body", "attachment_kind", "attachment_ref",
                "created_at", "delivered_via", "error"} <= columns

    def test_schema_version_bumped(self):
        from database.schema import SCHEMA_VERSION
        assert SCHEMA_VERSION >= 56

    def test_env_parsing(self, monkeypatch):
        monkeypatch.setenv("REACH_OUT_SILENCE_DAYS", "nonsense")
        assert reach_out.silence_days() == 42
        monkeypatch.setenv("REACH_OUT_SILENCE_DAYS", "0")
        assert reach_out.silence_days() == 1
        monkeypatch.delenv("REACH_OUT_SILENCE_DAYS")
        assert reach_out.silence_days() == 42
        monkeypatch.setenv("REACH_OUT_EMAIL", "   ")
        assert reach_out.email_address() is None
