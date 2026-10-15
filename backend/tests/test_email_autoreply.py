"""
Email auto-replies (card 04 6c / CAPABILITIES "Fix first"): Cass auto-replied
to every sender on every phase change and ignored quiet hours.

Auto-replies stay ON (whether Cass should auto-reply at all is Kohl's call),
but never during the owner's quiet hours, never twice to the same email, and
never to no-reply/automated senders, mailing lists or her own mail.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


@pytest.fixture
def owner(test_db):
    """An admin user (the owner whose quiet hours govern autonomous email)."""
    from database import get_db
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, display_name, is_admin, created_at, updated_at) "
            "VALUES ('owner-1', 'Kohl', 1, ?, ?)", (now, now))
    return "owner-1"


@pytest.fixture
def inbox(daemon_id):
    from email_organ import EmailManager
    return EmailManager(daemon_id)


class FakeSessionRunner:
    """Stands in for GenericSessionRunner: records which emails got a reply session."""

    def __init__(self):
        self.replied_to = []

    def register_tool_handlers(self, handlers):
        pass

    async def run_session(self, focus, **kwargs):
        self.replied_to.append(focus)
        return None


def _receive(inbox, sender, subject="hi", **extra):
    data = {"from": sender, "to": "cass@cass.example.com", "subject": subject,
            "body_plain": "hello", **extra}
    return asyncio.run(inbox.handle_inbound(data))


def _check(daemon_id, runner, respond_to_all=True):
    from scheduler.actions.email_handlers import check_inbox_action
    context = {"managers": {"daemon_id": daemon_id, "session_runner": runner},
               "runners": {}, "respond_to_all": respond_to_all}
    return asyncio.run(check_inbox_action(context))


def _replied_subjects(runner):
    return [focus.split("**Subject:** ")[1].split("\n")[0] for focus in runner.replied_to]


def test_replies_to_a_person_once(owner, inbox, daemon_id):
    runner = FakeSessionRunner()
    _receive(inbox, "Alice <alice@example.org>", subject="question", message_id="<m1@example.org>")

    first = _check(daemon_id, runner)
    second = _check(daemon_id, runner)

    assert first.data["auto_responded"] == 1
    assert second.data["email_count"] == 0
    assert _replied_subjects(runner) == ["question"]


@pytest.mark.parametrize("sender, extra, reason", [
    ("no-reply@service.example", {}, "no-reply"),
    ("Mailer <mailer-daemon@example.org>", {}, "no-reply"),
    ("updates@lists.example.org", {"List-Id": "<news.lists.example.org>"}, "mailing list"),
    ("bob@example.org", {"headers": {"Auto-Submitted": "auto-replied"}}, "auto-submitted"),
    ("bob@example.org", {"Precedence": "bulk"}, "precedence"),
])
def test_never_replies_to_automated_senders(owner, inbox, daemon_id, sender, extra, reason):
    runner = FakeSessionRunner()
    email = _receive(inbox, sender, **extra)

    result = _check(daemon_id, runner)

    assert runner.replied_to == []
    assert reason in result.data["skipped"][email.id]
    # Marked handled, so it isn't reconsidered on every phase change
    assert inbox.get_unprocessed() == []


def test_never_replies_to_own_mail(owner, inbox, daemon_id):
    runner = FakeSessionRunner()
    email = _receive(inbox, "Cass <cass@cass.example.com>")

    result = _check(daemon_id, runner)

    assert runner.replied_to == []
    assert result.data["skipped"][email.id] == "own sent mail"


def test_never_replies_twice_to_the_same_message(owner, inbox, daemon_id):
    """A reply already exists (e.g. sent by the chat tool), or the relay redelivers."""
    from database import get_db
    runner = FakeSessionRunner()
    answered = _receive(inbox, "carol@example.org", message_id="<answered@example.org>")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO emails (id, daemon_id, direction, status, from_address, to_address, "
            "in_reply_to, created_at) VALUES ('out-1', ?, 'outbound', 'sent', "
            "'cass@cass.example.com', 'carol@example.org', '<answered@example.org>', ?)",
            (daemon_id, datetime.now().isoformat()))

    first = _receive(inbox, "dan@example.org", subject="original", message_id="<dup@example.org>")
    _check(daemon_id, runner)
    redelivered = _receive(inbox, "dan@example.org", subject="original", message_id="<dup@example.org>")
    result = _check(daemon_id, runner)

    assert _replied_subjects(runner) == ["original"]
    assert result.data["skipped"] == {redelivered.id: "duplicate delivery"}
    assert first.id != redelivered.id
    assert answered.id not in [e.id for e in inbox.get_unprocessed()]


def test_quiet_hours_defer_replies(owner, inbox, daemon_id):
    from quiet_hours import get_quiet_hours_manager
    runner = FakeSessionRunner()
    get_quiet_hours_manager().update_preference(owner, enabled=True, start_hour=0, end_hour=0,
                                                timezone="UTC")
    # start == end means "never quiet" in is_quiet_hours; use a window that covers now
    now_hour = datetime.now(timezone.utc).hour
    get_quiet_hours_manager().update_preference(owner, start_hour=now_hour,
                                                end_hour=(now_hour + 1) % 24)
    _receive(inbox, "erin@example.org", subject="late night")

    deferred = _check(daemon_id, runner)
    assert deferred.data.get("deferred") is True
    assert runner.replied_to == []
    assert len(inbox.get_unprocessed()) == 1  # still waiting

    get_quiet_hours_manager().update_preference(owner, enabled=False)
    _check(daemon_id, runner)
    assert _replied_subjects(runner) == ["late night"]


def test_claim_is_atomic(inbox, daemon_id):
    """Two overlapping checks can't both claim the same email."""
    email = _receive(inbox, "frank@example.org")
    assert inbox.mark_processing(email.id) is True
    assert inbox.mark_processing(email.id) is False


def test_quiet_hours_window(owner):
    from quiet_hours import get_quiet_hours_manager, owner_in_quiet_hours
    manager = get_quiet_hours_manager()
    manager.update_preference(owner, enabled=True, start_hour=22, end_hour=7, timezone="UTC")

    assert owner_in_quiet_hours(datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc))
    assert owner_in_quiet_hours(datetime(2026, 1, 1, 6, 59, tzinfo=timezone.utc))
    assert not owner_in_quiet_hours(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
