"""The record (record.py): dated, attributed, sourced; reads only; names what it
couldn't read; its own token."""
import json
import subprocess
from datetime import datetime
from types import SimpleNamespace

import record as R

NOW = datetime(2026, 11, 18, 9, 0)
EVENTS = [
    {"seq": 10, "planSlug": "honesty-6n7tu", "actor": {"name": "cass"}, "action": "item-status",
     "detail": {"title": "Reach out to Kohl", "status": "done", "resolution": "sent at 12:01"},
     "at": "2026-11-18T04:20:00Z"},
    {"seq": 11, "planSlug": "honesty-6n7tu", "actor": {"name": "cass"}, "action": "comment",
     "detail": {"body": "thinking"}, "at": "2026-11-18T04:21:00Z"},
    {"seq": 12, "planSlug": "house-plan", "actor": {"name": "robokohl"}, "action": "item-added",
     "detail": {"title": "not hers"}, "at": "2026-11-18T04:22:00Z"},
    {"seq": 13, "planSlug": "cass-s-asks-x", "actor": {"name": "jaryk"}, "action": "phase-approved",
     "detail": {"phase": "1"}, "at": "2026-11-18T04:23:00Z"},
]
PLANS = {"honesty-6n7tu": "Direct Honesty", "cass-s-asks-x": "Cass's asks"}


def _data(tmp_path):
    (tmp_path / "self_account").mkdir()
    (tmp_path / "self_account" / "changes.jsonl").write_text(
        json.dumps({"at": "2026-11-17T23:19:04", "changes": ["New tool: set_routine"]}) + "\n")
    (tmp_path / "social" / "bluesky").mkdir(parents=True)
    (tmp_path / "social" / "bluesky" / "posted.jsonl").write_text(
        json.dumps({"at": "2026-11-17T10:00:00", "kind": "post", "text": "first light", "uri": "at://x"}) + "\n"
        + json.dumps({"at": "2026-11-17T11:00:00", "kind": "dm", "text": "private words", "to": "ann"}) + "\n")
    return tmp_path


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    (repo / "f").write_text("x")
    run("add", "f")
    run("-c", "user.name=Daedalus", "-c", "user.email=d@x", "commit", "-q", "-m", "A change she asked for")
    return repo


def test_entries_are_dated_attributed_and_sourced(tmp_path):
    reach = [SimpleNamespace(id="r1", kind="say", body="I'm not ready yet.", created_at="2026-11-17T12:01:00",
                             delivered_via=[{"channel": "app", "ok": True}])]
    rec = R.build(days=30, data_dir=_data(tmp_path), now=NOW, plans=lambda: (EVENTS, PLANS),
                  reach_outs=lambda: reach, repo=_repo(tmp_path))
    by = {(e["kind"], e["title"]): e for e in rec["entries"]}
    done = by[("plan", "item status: Reach out to Kohl -> done")]
    assert done["who"] == "cass" and done["source"] == "Plans event #10 (honesty-6n7tu)"
    assert "sent at 12:01" in done["detail"]
    assert ("ask", "phase approved: 1") in by and by[("ask", "phase approved: 1")]["who"] == "jaryk"
    assert not any("not hers" in e["title"] for e in rec["entries"])
    assert not any(e["title"].startswith("comment") for e in rec["entries"])
    assert by[("change", "New tool: set_routine")]["source"] == "self_account/changes.jsonl:1"
    assert by[("world", "reached out to Kohl (say) via app")]["detail"] == "I'm not ready yet."
    assert by[("world", "bluesky: post")]["detail"] == "first light"
    assert by[("world", "bluesky: dm (ann)")]["detail"] == "", "a DM is recorded as happening, not its words"
    code = by[("code", "A change she asked for")]
    assert code["who"] == "daedalus" and code["source"].startswith("commit ")
    assert rec["unavailable"] == [] and len(rec["digest"]) == 64
    md = R.to_markdown(rec)
    assert "## Her plans" in md and "_source: Plans event #10 (honesty-6n7tu)_" in md and rec["digest"] in md


def test_what_couldnt_be_read_is_named(tmp_path):
    def down():
        raise RuntimeError("Babelr isn't connected")
    rec = R.build(days=7, data_dir=tmp_path, now=NOW, plans=down, reach_outs=lambda: [], repo=tmp_path / "nope")
    assert any(u.startswith("Plans: Babelr isn't connected") for u in rec["unavailable"])
    assert any(u.startswith("vessel commits") for u in rec["unavailable"])
    assert "Not included (couldn't be read)" in R.to_markdown(rec)


def test_long_text_is_cut_with_a_marker_not_reworded():
    e = R._entry("t", "cass", "world", "x", "s", "a" * (R.TEXT_CAP + 50))
    assert e["detail"].startswith("a" * R.TEXT_CAP) and "[... 50 more characters]" in e["detail"]


def test_record_tokens_are_their_own(tmp_path):
    token = R.mint_token("plugin", tmp_path)
    assert R.token_ok(token, tmp_path)
    assert not R.token_ok("room_" + token[7:], tmp_path) and not R.token_ok(None, tmp_path)
    stored = (tmp_path / "record" / "tokens.json").read_text()
    assert token not in stored


def test_the_routes_need_a_record_token(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.record as RR
    app = FastAPI()
    app.include_router(RR.router)
    monkeypatch.setattr(R, "token_ok", lambda t, data_dir=None: t == "record_ok")
    monkeypatch.setattr(R, "build", lambda days=30: {"days": days, "entries": [], "generated_at": "g",
                                                       "digest": "d", "unavailable": [], "spend_by_day": []})
    c = TestClient(app)
    assert c.get("/record").status_code == 401
    assert c.get("/record", headers={"Authorization": "Bearer room_x"}).status_code == 401
    assert c.get("/record?days=7", headers={"Authorization": "Bearer record_ok"}).json()["days"] == 7
    assert c.get("/record.md", headers={"Authorization": "Bearer record_ok"}).text.startswith("# Cass: the record")


def test_reach_outs_are_read_for_her_daemon_id(monkeypatch):
    """The first version passed her daemon's label where its id belongs and read
    nothing, silently (2026-11-18)."""
    import database
    import reach_out
    seen = {}
    monkeypatch.setattr(database, "get_daemon_id", lambda: "daemon-uuid")
    monkeypatch.setattr(reach_out, "find_primary_partner", lambda d: seen.setdefault("partner_for", d) and "kohl-id")

    class Manager:
        def __init__(self, daemon_id):
            seen["manager_for"] = daemon_id

        def history(self, user_id, limit=20):
            seen["user"] = user_id
            return ["one"]
    monkeypatch.setattr(reach_out, "ReachOutManager", Manager)
    assert R._live_reach_outs() == ["one"]
    assert seen == {"partner_for": "daemon-uuid", "manager_for": "daemon-uuid", "user": "kohl-id"}


def test_she_can_read_her_record(monkeypatch):
    import asyncio
    import self_account
    from agent_loop.spec import session_spec
    monkeypatch.setattr(R, "build", lambda days=7: {"days": days, "entries": [], "generated_at": "g",
                                                     "digest": "d", "unavailable": [], "spend_by_day": [],
                                                     "kinds": R.KIND_WORDS})
    out = asyncio.run(self_account.execute_self_account_tool("my_record", {"days": 3}))
    assert out["success"] and out["result"].startswith("# Cass: the record, last 3 days")
    assert any(t["name"] == "my_record" for t in self_account.HOW_I_WORK_TOOLS)
    assert "my_record" in session_spec("long_term_planning").tool_names()
