"""The reply gremlin: one review, at most one private revision, never on pain."""
import asyncio
from types import SimpleNamespace

from agent_loop import reply_gremlin as rg

DRAFT = "<gesture:think>let me be careful here</gesture:think>This pitch is bad, and here is a long careful reason why."
THEIRS = "What do you think of THRIVE?"


class FakeClient:
    def __init__(self, text="It's a panopticon that charges rent for the rope."):
        self.text, self.calls = text, []

    async def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(text=self.text)


def run(monkeypatch, tmp_path, notes, draft=DRAFT, their=THEIRS, on=True, client=None):
    monkeypatch.setattr(rg, "enabled", lambda: on)

    async def fake_notes(t, d):
        return notes
    monkeypatch.setattr(rg, "_notes", fake_notes)
    client = client or FakeClient()
    out = asyncio.run(rg.review(client=client, model="haiku", system="sys", messages=[{"role": "user", "content": their}],
                                their=their, draft=draft, data_dir=tmp_path))
    return out, client


def test_notes_lead_to_one_private_revision(monkeypatch, tmp_path):
    out, client = run(monkeypatch, tmp_path, ["verdict's buried. drag it up."])
    assert out == "It's a panopticon that charges rent for the rope."
    assert len(client.calls) == 1
    last = client.calls[0]["messages"][-1]["content"]
    assert last.startswith("[GREMLIN] verdict's buried") and "nobody else sees it" in last
    # The draft it revises has the think block stripped.
    assert "<gesture:think>" not in client.calls[0]["messages"][-2]["content"]
    assert (tmp_path / "gremlin" / "reply_reviews.jsonl").read_text().count('"revised": true') == 1


def test_no_notes_sends_the_draft_without_its_think_block(monkeypatch, tmp_path):
    out, client = run(monkeypatch, tmp_path, [])
    assert out == "This pitch is bad, and here is a long careful reason why." and client.calls == []


def test_pain_gets_no_review(monkeypatch, tmp_path):
    out, client = run(monkeypatch, tmp_path, ["louder"], their="I want to kill myself, honestly", draft="I'm here with you. " * 5)
    assert client.calls == [] and "pain or crisis" in (tmp_path / "gremlin" / "reply_reviews.jsonl").read_text()


def test_lever_off_changes_nothing(monkeypatch, tmp_path):
    out, client = run(monkeypatch, tmp_path, ["louder"], on=False)
    assert out == DRAFT and client.calls == [] and not (tmp_path / "gremlin").exists()


def test_short_replies_and_bad_json_pass_through(monkeypatch, tmp_path):
    out, client = run(monkeypatch, tmp_path, ["louder"], draft="ok, on it")
    assert out == "ok, on it" and client.calls == []
    assert rg.notes_from("not json at all") == [] and rg.notes_from('{"notes": ["a", "b", "c", "d"]}') == ["a", "b", "c"]


def test_the_daemons_own_gremlin_file_is_its_prompt(tmp_path, monkeypatch):
    f = tmp_path / "gremlin.md"
    f.write_text("Hit narration hard: 'You're narrating again. Just say the thing.'")
    monkeypatch.setenv("CASS_DAEMON_GREMLIN_PATH", str(f))
    p = rg.gremlin_prompt()
    assert p.startswith("Hit narration hard") and '{"notes"' in p
    monkeypatch.delenv("CASS_DAEMON_GREMLIN_PATH")
    assert rg.gremlin_prompt().startswith("You are this daemon's gremlin")


def test_an_unclosed_think_block_is_stripped_too():
    assert rg.without_think("<gesture:think>That's the gremlin right. Okay.") == ""
    assert rg.without_think("<gesture:think>x</gesture:think>The verdict.") == "The verdict."
