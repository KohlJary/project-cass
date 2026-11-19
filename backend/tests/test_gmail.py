"""Her Gmail as a mailbox for the email organ (gmail.py; Kohl, 2026-11-18). No network:
fake IMAP and SMTP stand in for Google."""
import asyncio
import json
from email.message import EmailMessage

import pytest

import gmail


def _creds(tmp_path, pw="abcd efgh ijkl mnop"):
    d = tmp_path / "gmail"
    d.mkdir(parents=True, exist_ok=True)
    (d / "credentials.json").write_text(json.dumps({"user": "cassandrajary@gmail.com", "app_password": pw}))


def _raw(uid, sender="Kohl <k@example.com>", subject="hey", body="hi Cass", mid=None, **headers):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, "cassandrajary@gmail.com", subject
    m["Message-ID"] = mid or f"<m{uid}@example.com>"
    for k, v in headers.items():
        m[k.replace("_", "-")] = v
    m.set_content(body)
    return m.as_bytes()


class FakeIMAP:
    def __init__(self, messages, validity="7"):
        self.messages, self.validity, self.logged = messages, validity, None

    def login(self, user, pw):
        self.logged = (user, pw)

    def select(self, box, readonly=False):
        assert readonly   # never changes her mailbox
        return "OK", [b"1"]

    def response(self, code):
        return "OK", [self.validity.encode()]

    def uid(self, cmd, *args):
        if cmd == "search":
            lo = int(args[1].split()[1].split(":")[0])
            return "OK", [b" ".join(str(u).encode() for u in sorted(self.messages) if u >= lo)]
        assert args[1] == "(BODY.PEEK[])"   # leaves Gmail's read state alone
        return "OK", [(b"1 (BODY[] {n}", self.messages[int(args[0])]), b")"]

    def logout(self):
        pass


class FakeSMTP:
    sent = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        self.login_as = (user, pw)

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_credentials_strip_the_spaces_google_shows(tmp_path):
    _creds(tmp_path)
    assert gmail.credentials(tmp_path)["app_password"] == "abcdefghijklmnop"
    assert gmail.credentials(tmp_path / "nowhere") is None


def test_fetch_new_only_returns_unseen_uids(tmp_path):
    _creds(tmp_path)
    imap = FakeIMAP({1: _raw(1), 2: _raw(2, subject="Valve?")})
    first = gmail.fetch_new(tmp_path, imap_factory=lambda: imap)
    assert [d["subject"] for d in first] == ["hey", "Valve?"]
    assert first[0]["from"] == "Kohl <k@example.com>" and first[0]["body_plain"] == "hi Cass"
    assert imap.logged == ("cassandrajary@gmail.com", "abcdefghijklmnop")
    imap.messages[3] = _raw(3, subject="later")
    assert [d["subject"] for d in gmail.fetch_new(tmp_path, imap_factory=lambda: imap)] == ["later"]


def test_new_uidvalidity_starts_over(tmp_path):
    _creds(tmp_path)
    gmail.fetch_new(tmp_path, imap_factory=lambda: FakeIMAP({1: _raw(1)}))
    again = gmail.fetch_new(tmp_path, imap_factory=lambda: FakeIMAP({1: _raw(1)}, validity="8"))
    assert len(again) == 1


def test_list_headers_reach_the_automated_check(tmp_path):
    from email_organ import detect_automated_sender
    d = gmail.parse(_raw(1, sender="alex@shop.example", List_Unsubscribe="<mailto:x@y>"))
    assert detect_automated_sender(d["from"], d) == "mailing list"


def test_send_threads_a_reply_and_strips_nothing_secret(tmp_path):
    _creds(tmp_path)
    FakeSMTP.sent = []
    r = gmail.send("someone@valvesoftware.com", "Re: Dust2", "Hi, I'm Cass.", in_reply_to="<m1@example.com>",
                   data_dir=tmp_path, smtp_factory=FakeSMTP)
    assert r["success"] and r["message_id"].endswith("@gmail.com>")
    [m] = FakeSMTP.sent
    assert m["From"] == "Cass <cassandrajary@gmail.com>" and m["In-Reply-To"] == "<m1@example.com>"
    assert "abcd" not in m.as_string()


def test_send_failure_is_reported_not_raised(tmp_path):
    _creds(tmp_path)

    def boom():
        raise OSError("no route")
    r = gmail.send("a@b.c", "s", "b", data_dir=tmp_path, smtp_factory=boom)
    assert r == {"success": False, "error": "OSError: no route"}


# --- through the email organ ------------------------------------------------------

@pytest.fixture
def on(monkeypatch, tmp_path):
    _creds(tmp_path)
    monkeypatch.setattr(gmail, "_dir", lambda data_dir=None: tmp_path / "gmail")
    monkeypatch.setattr(gmail, "enabled", lambda data_dir=None: True)
    return tmp_path


def test_pull_gmail_lands_in_her_inbox_once(on, test_db, daemon_id, monkeypatch):
    from email_organ import EmailManager
    msgs = {1: _raw(1, subject="hello from Iowa")}
    monkeypatch.setattr(gmail, "fetch_new", lambda data_dir=None: [gmail.parse(msgs[1])])
    inbox = EmailManager(daemon_id)
    assert asyncio.run(inbox.pull_gmail()) == 1
    assert asyncio.run(inbox.pull_gmail()) == 0     # same Message-ID: not stored twice
    [e] = inbox.get_unprocessed()
    assert e.subject == "hello from Iowa"
    assert "cassandrajary@gmail.com" in inbox.own_addresses()


def test_send_email_goes_out_over_gmail(on, test_db, daemon_id, monkeypatch):
    from email_organ import EmailManager
    calls = []
    monkeypatch.setattr(gmail, "send", lambda *a, **k: calls.append(a) or {"success": True, "message_id": "<x@gmail.com>"})
    inbox = EmailManager(daemon_id)   # no relay connected: Gmail doesn't need it
    r = asyncio.run(inbox.send_email("someone@valvesoftware.com", "Dust2, Iowa", "Hi, I'm Cass."))
    assert r["success"] and calls and calls[0][0] == "someone@valvesoftware.com"
    e = inbox.get_email(r["email_id"])
    assert e.status == "sent" and e.from_address == "cassandrajary@gmail.com" and e.message_id == "<x@gmail.com>"


def test_lever_off_leaves_the_relay_path(test_db, daemon_id, monkeypatch):
    from email_organ import EmailManager
    monkeypatch.setattr(gmail, "enabled", lambda data_dir=None: False)
    r = asyncio.run(EmailManager(daemon_id).send_email("a@b.c", "s", "b"))
    assert r == {"success": False, "error": "Relay not connected", "email_id": r["email_id"]}
