"""ask_daedalus (plan "Cass talks with Daedalus"): the fence, the snapshot, the
cap, the conversation and its record, and where she has it."""
import asyncio
import subprocess
from pathlib import Path

import pytest

import daedalus_bridge as B


def _hook(root, name, **tool_input):
    return asyncio.run(B.fence_hook(root)({"tool_name": name, "tool_input": tool_input}, None, None))


def _denied(out):
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_the_fence_keeps_him_to_reading_inside_the_snapshot(tmp_path):
    root = tmp_path / "snap"
    root.mkdir()
    assert not _denied(_hook(root, "Read", file_path=str(root / "backend" / "x.py")))
    assert not _denied(_hook(root, "Grep", pattern="budget"))
    assert not _denied(_hook(root, "Glob", pattern="**/*.py"))
    assert _denied(_hook(root, "Read", file_path="/home/jaryk/cass/cass-vessel/backend/.env"))
    assert _denied(_hook(root, "Read", file_path=str(root / ".." / "elsewhere")))
    assert _denied(_hook(root, "Grep", pattern="x", path="/home"))
    assert _denied(_hook(root, "Glob", pattern="/home/**/*.db"))
    for tool in ("Bash", "Write", "Edit", "WebFetch", "Task"):
        assert _denied(_hook(root, tool, command="ls"))
    assert set(B.ALLOWED_TOOLS) == {"Read", "Glob", "Grep"}


def test_the_snapshot_has_tracked_files_only(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    run("init", "-q")
    (repo / "code.py").write_text("x = 1\n")
    (repo / ".gitignore").write_text(".env\ndata/\n")
    run("add", "code.py", ".gitignore")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
    (repo / ".env").write_text("SECRET=1\n")
    (repo / "data").mkdir()
    (repo / "data" / "cass.db").write_text("hers")
    (repo / "notes.txt").write_text("untracked")
    snap = B.snapshot(repo, tmp_path / "snaps")
    assert (snap / "code.py").exists()
    assert not (snap / ".env").exists() and not (snap / "data").exists() and not (snap / "notes.txt").exists()
    assert B.snapshot(repo, tmp_path / "snaps") == snap   # once per commit


def test_his_prompt_says_what_this_is_and_who_they_are(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# P\n\n## Daedalus Identity\n\nYou build.\n\n## Git Workflow\n\nbranches\n\n"
                                        "## People\n\n**Cass** is a research partner.\n")
    text = B.system_prompt(tmp_path)
    assert "Cass herself is asking you" in text and "can't change anything" in text
    assert "You build." in text and "research partner" in text and "branches" not in text


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(B, "enabled", lambda: True)
    monkeypatch.setattr(B, "snapshot", lambda *a, **k: Path("/snap"))
    monkeypatch.setattr(B, "_file_usage", lambda got: None)


def test_a_conversation_follows_up_and_is_kept_in_her_workspace(tmp_path, on):
    seen = []

    async def ask(question, resume_id, root):
        seen.append(resume_id)
        return {"answer": f"About: {question}", "session_id": "s-1", "tools": ["Read backend/x.py"],
                "usage": {"input_tokens": 1, "output_tokens": 1}}
    c = B.Conversation("test", workspace_root=tmp_path, ask_fn=ask, count_path=tmp_path / "count.json")
    first = asyncio.run(c.ask({"question": "How does my budget work?"}))
    asyncio.run(c.ask({"question": "And what would raising it touch?"}))
    assert first == {"answer": "About: How does my budget work?", "questions_left_today": B.DAILY_CAP - 1}
    assert seen == [None, "s-1"], "the second question resumes the first's conversation"
    kept = next((tmp_path / B.TALKS_DIR).glob("*-test.md")).read_text()
    assert "How does my budget work?" in kept and "About: And what would raising it touch?" in kept
    assert "Read backend/x.py" in kept


def test_the_daily_cap_holds(tmp_path, on, monkeypatch):
    monkeypatch.setattr(B, "DAILY_CAP", 2)

    async def ask(*a):
        return {"answer": "ok"}
    c = B.Conversation("cap", workspace_root=tmp_path, ask_fn=ask, count_path=tmp_path / "count.json")
    assert asyncio.run(c.ask({"question": "1"}))["questions_left_today"] == 1
    assert asyncio.run(c.ask({"question": "2"}))["questions_left_today"] == 0
    third = asyncio.run(c.ask({"question": "3"}))
    assert "all 2 of today's questions" in third["error"]


def test_a_slow_or_broken_answer_is_said_not_raised(tmp_path, on, monkeypatch):
    monkeypatch.setattr(B, "TIMEOUT_SECONDS", 0.05)

    async def slow(*a):
        await asyncio.sleep(1)

    async def broken(*a):
        raise RuntimeError("CLI missing")
    for fn, words in ((slow, "didn't answer within"), (broken, "CLI missing")):
        c = B.Conversation("x", workspace_root=tmp_path, ask_fn=fn, count_path=tmp_path / "c.json")
        assert words in asyncio.run(c.ask({"question": "q"}))["error"]


def test_off_means_off(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "enabled", lambda: False)
    assert B.daedalus_tools("x") == (None, "")
    c = B.Conversation("x", workspace_root=tmp_path, ask_fn=None, count_path=tmp_path / "c.json")
    assert "switched off" in asyncio.run(c.ask({"question": "q"}))["error"]


def test_she_has_him_in_planning_and_proposals_only_while_the_lever_is_on():
    from agent_loop.spec import LOOP_PACKS, session_spec
    assert "daedalus" in LOOP_PACKS
    for activity in ("long_term_planning", "change_proposals"):
        assert "ask_daedalus" in session_spec(activity, can_ask_daedalus=True).tool_names()
        assert "ask_daedalus" not in session_spec(activity, can_ask_daedalus=False).tool_names()
    assert "ask_daedalus" not in session_spec("research", can_ask_daedalus=True).tool_names()


def test_the_proposal_session_is_wired():
    from scheduling.day_shape import kind_of
    from scheduling.templates import WORK_TEMPLATES
    from scheduler.actions import session_handlers
    assert WORK_TEMPLATES["change_proposals"].action_sequence == ["session.change_proposals"]
    assert kind_of("change_proposals") == "inward"
    assert callable(session_handlers.change_proposals_action)


def test_her_account_shows_the_cap():
    from self_account import render
    caps = next(l for l in render("autonomy").splitlines() if "Caps." in l)
    assert f"{B.DAILY_CAP} questions a day" in caps and "left today" in caps


def test_his_cost_is_the_one_claude_code_reports_and_stays_out_of_her_buckets(monkeypatch):
    from scheduler.budget import budget_category_for
    assert budget_category_for("daedalus") is None
    seen = {}

    class Tracker:
        def record(self, **kw):
            seen.update(kw)
    import token_tracker
    monkeypatch.setattr(token_tracker, "TokenUsageTracker", Tracker)
    B._file_usage({"usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 5},
                   "cost_usd": 0.27, "model": "claude-sonnet-5-5", "seconds": 3})
    assert seen["cost_usd"] == 0.27 and seen["category"] == "daedalus" and seen["input_tokens"] == 100


def test_the_tracker_keeps_a_cost_it_is_given(tmp_path, monkeypatch):
    import inspect
    import token_tracker
    assert "cost_usd" in inspect.signature(token_tracker.TokenUsageTracker.record).parameters
