"""work_with_daedalus: Daedalus inside one of her workshop projects. The fence,
uncommitted changes coming back to her, the shared count, and where she has it."""
import asyncio
import os
import subprocess
from pathlib import Path

import pytest

import daedalus_bridge as B
import workshop as W


def _denied(out):
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


@pytest.fixture
def project(tmp_path):
    r = W.new("Little Tool", "software", "A small tool.", data_dir=tmp_path)
    p = W.root(tmp_path) / r["project"]
    (tmp_path / "github").mkdir()
    (tmp_path / "github" / "credentials.json").write_text('{"token": "x"}')
    return tmp_path, r["project"], p


def _hook(p, name, **ti):
    h = B.fence_hook(p, allowed=B.PROJECT_ALLOWED, protected=B.PROJECT_PROTECTED, reason="r")
    return asyncio.run(h({"tool_name": name, "tool_input": ti}, None, None))


def test_the_fence_keeps_him_inside_the_project(project):
    data, slug, p = project
    assert not _denied(_hook(p, "Read", file_path=str(p / "PROJECT.md")))
    assert not _denied(_hook(p, "Write", file_path=str(p / "src" / "main.py")))
    assert not _denied(_hook(p, "Edit", file_path="PROJECT.md"))
    assert not _denied(_hook(p, "mcp__workshop__run", command="python3 main.py"))
    assert _denied(_hook(p, "Read", file_path=str(data / "github" / "credentials.json")))
    assert _denied(_hook(p, "Read", file_path=str(p / ".." / ".." / "github" / "credentials.json")))
    assert _denied(_hook(p, "Write", file_path=str(p / ".git" / "config")))
    assert _denied(_hook(p, "Edit", file_path=".workshop.json"))
    assert _denied(_hook(p, "Grep", pattern="token", path=str(data)))
    assert _denied(_hook(p, "Glob", pattern=str(data) + "/**/*.json"))
    for tool in ("Bash", "WebFetch", "Task", "MultiEdit"):
        assert _denied(_hook(p, tool, command="ls"))


def test_a_symlink_out_of_the_project_is_refused(project):
    data, slug, p = project
    os.symlink(data / "github", p / "escape")
    assert _denied(_hook(p, "Read", file_path=str(p / "escape" / "credentials.json")))


def test_his_changes_come_back_uncommitted(project, tmp_path, monkeypatch):
    data, slug, p = project
    monkeypatch.setattr(B, "enabled", lambda: True)
    commits_before = W.log(slug, data_dir=data)

    async def fake(request, resume_id, root, **kw):
        (root / "main.py").write_text("print('hi')\n")
        (root / "PROJECT.md").write_text((root / "PROJECT.md").read_text() + "\nmore\n")
        return {"answer": "I added main.py.", "session_id": "s1", "usage": {}, "tools": ["Write main.py"]}

    conv = B.ProjectConversation("workshop-little-tool", default_project=slug, data_dir=data, ask_fn=fake,
                                 workspace_root=tmp_path / "ws", count_path=tmp_path / "count.json")
    out = asyncio.run(conv.work({"request": "Add a main.py that says hi"}))
    assert out["answer"] == "I added main.py."
    assert any("main.py" in f for f in out["uncommitted"]) and any("PROJECT.md" in f for f in out["uncommitted"])
    assert "print('hi')" in out["diff"] and "+more" in out["diff"]
    assert W.log(slug, data_dir=data) == commits_before            # nothing committed for her
    assert conv.resume_ids[slug] == "s1"
    assert B.asked_today(tmp_path / "count.json") == 1             # the same daily count
    talk = list((tmp_path / "ws" / B.TALKS_DIR).glob("*.md"))
    assert talk and "Add a main.py" in talk[0].read_text()


def test_no_project_no_lever_no_cap(project, tmp_path, monkeypatch):
    data, slug, p = project
    conv = B.ProjectConversation("w", data_dir=data, ask_fn=None, count_path=tmp_path / "c.json",
                                 workspace_root=tmp_path / "ws")
    monkeypatch.setattr(B, "enabled", lambda: False)
    assert "switched off" in asyncio.run(conv.work({"request": "x", "project": slug}))["error"]
    monkeypatch.setattr(B, "enabled", lambda: True)
    assert "which project" in asyncio.run(conv.work({"request": "x"}))["error"]
    assert "no project" in asyncio.run(conv.work({"request": "x", "project": "nope"}))["error"]
    for _ in range(B.DAILY_CAP):
        B._count_one(tmp_path / "c.json")
    assert asyncio.run(conv.work({"request": "x", "project": slug}))["questions_left_today"] == 0


def test_workshop_session_offers_him_by_the_lever(monkeypatch):
    import workshop_turn as T
    monkeypatch.setattr(B, "enabled", lambda: True)
    tools = B.project_tools("workshop-x", default_project="x")
    assert set(tools) == {"work_with_daedalus"}
    monkeypatch.setattr(B, "enabled", lambda: False)
    assert B.project_tools("workshop-x") is None
    assert "work_with_daedalus" in T.DAEDALUS_LINE
