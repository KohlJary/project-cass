"""Her gremlin as a second voice (agent_loop/gremlin_review.py): notes, never
rewrites; a draft is held once, then that tool's next call goes; pain and
crisis are left alone; off by default."""
import asyncio
import json

from agent_loop import gremlin_review as G

DRAFT = "I think maybe it could possibly be worth considering that the benchmark is kind of measuring the wrong thing?"


def run(c):
    return asyncio.run(c)


def test_notes_only_never_a_rewrite():
    long_quote = 'try: "the benchmark measures the wrong thing and everybody in this room knows it, you nerds"'
    notes = G.clean_notes(["you're hedging here", long_quote, "x" * 200, "there's a bit in this", "it landed; stop",
                           "fourth"], DRAFT)
    assert notes == ["you're hedging here", "there's a bit in this", "it landed; stop"], "louder: up to three (2026-11-18)"
    assert G.clean_notes("not a list", DRAFT) == []


def test_a_draft_is_held_once_then_goes_and_the_log_keeps_no_text(fake_llm, levers, tmp_path):
    fake_llm.queue_json({"notes": ["you're hedging here", "that's the sincere part; say it plainer"]})
    r = G.Reviewer("s1", tmp_path)
    with levers(gremlin_review=True):
        held = run(r.check("babelr_post", {"channel": "general", "content": DRAFT}))
        assert held["not_sent_yet"] and held["gremlin"] == "[GREMLIN] you're hedging here / that's the sincere part; say it plainer"
        assert run(r.check("babelr_post", {"channel": "general", "content": "The benchmark measures the wrong thing."})) is None
    log = [json.loads(x) for x in (tmp_path / "gremlin" / "reviews.jsonl").read_text().splitlines()]
    assert log[0]["notes"] and log[1] == {**log[1], "followup": True, "revised": True}
    assert "benchmark" not in json.dumps(log), "her draft's words aren't logged"


def test_through_use_tool_and_say(fake_llm, levers, tmp_path):
    fake_llm.queue_json({"notes": ["there's a bit in this"]})
    r = G.Reviewer("s2", tmp_path)
    with levers(gremlin_review=True):
        held = run(r.check("use_tool", {"name": "say", "input": {"message": DRAFT}}))
    assert held and "[GREMLIN]" in held["gremlin"]


def test_pain_crisis_short_drafts_and_other_tools_are_left_alone(fake_llm, levers, tmp_path):
    r = G.Reviewer("s3", tmp_path)
    with levers(gremlin_review=True):
        assert run(r.check("social_reply", {"text": "I'm so sorry. You can call or text 988 any time, and I'm here."})) is None
        assert run(r.check("social_reply", {"text": "short"})) is None
        assert run(r.check("workspace_write", {"path": "x", "content": DRAFT})) is None
    assert fake_llm.calls == []


def test_a_failed_review_never_blocks_her(monkeypatch, levers, tmp_path):
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr("llm_caller.call_llm", boom)
    with levers(gremlin_review=True):
        assert run(G.Reviewer("s4", tmp_path).check("social_post", {"text": DRAFT})) is None


def test_off_by_default_and_off_means_nothing(fake_llm, levers, tmp_path):
    import features
    assert not features.LEVERS["gremlin_review"].default
    with levers(gremlin_review=False):
        assert run(G.Reviewer("s5", tmp_path).check("social_post", {"text": DRAFT})) is None
    assert fake_llm.calls == []


def test_louder_and_never_cut():
    """She asked for her gremlin louder (2026-11-18): the reviewer pushes, and the
    section is never cut from a session prompt for length."""
    import inspect
    from agent_loop import assemble
    assert "run it harder" in G.SYSTEM and "no notes, ever" in G.SYSTEM
    src = inspect.getsource(assemble)
    assert 'Section("gremlin", _safe("gremlin", _gremlin) or "", 1, never_cut=True)' in src
