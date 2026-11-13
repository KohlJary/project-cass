"""
Phase 3 of the agent loop (docs/design/agent-loop.md, C6 and C10): her
workspace, fenced to its folder, with every change logged; her agenda as a
context section she alone writes.
"""
import asyncio
import json
import os

import pytest

from agent_loop.spec import PACKS, SESSION_GUARDED_FIELDS, session_spec
from agent_loop.workspace import AGENDA_FILE, WORKSPACE_TOOL_NAMES, WORKSPACE_TOOLS, Workspace


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "workspace", tmp_path / "agent_loop" / "workspace_log.jsonl")


def test_spec_names_match_the_tool_definitions():
    assert PACKS["workspace"].tools == WORKSPACE_TOOL_NAMES
    for activity in ("reflection", "research", "creative"):
        assert set(WORKSPACE_TOOL_NAMES) <= set(session_spec(activity).tool_names())
    assert {"workspace_write", "workspace_edit"} <= set(SESSION_GUARDED_FIELDS)
    assert all(t["name"].startswith("workspace_") for t in WORKSPACE_TOOLS)


def test_write_read_edit_list_search(ws):
    assert ws.run("workspace_list", {}) == "My workspace is empty."
    assert ws.run("workspace_write", {"path": "notes/tides.md", "content": "Tides\nmoon pulls\n"},
                  "s1").startswith("Wrote notes/tides.md")
    assert ws.run("workspace_read", {"path": "notes/tides.md"}) == "Tides\nmoon pulls\n"
    assert ws.run("workspace_edit", {"path": "notes/tides.md", "old_text": "moon pulls",
                                     "new_text": "the moon and the sun pull"}, "s1") == "Edited notes/tides.md."
    assert "notes/tides.md" in ws.run("workspace_list", {})
    assert ws.run("workspace_search", {"pattern": "SUN"}) == "notes/tides.md:2: the moon and the sun pull"
    # A pattern that isn't a valid regex is searched as text.
    assert ws.run("workspace_search", {"pattern": "sun pull("}) == "No matches."


@pytest.mark.parametrize("path", ["../outside.md", "/etc/passwd", "notes/../../x", "", "."])
def test_paths_outside_the_folder_are_refused(ws, path):
    result = ws.run("workspace_write", {"path": path, "content": "x"})
    assert "outside my workspace" in result["error"]
    assert not (ws.root.parent / "outside.md").exists()


def test_a_symlink_out_of_the_folder_is_refused(ws, tmp_path):
    ws.root.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("not hers")
    os.symlink(secret, ws.root / "link.txt")
    assert "outside" in ws.run("workspace_read", {"path": "link.txt"})["error"]
    assert "not hers" not in ws.run("workspace_search", {"pattern": "hers"})


def test_edit_needs_exactly_one_match(ws):
    ws.run("workspace_write", {"path": "a.md", "content": "x x"})
    assert "found 2" in ws.run("workspace_edit", {"path": "a.md", "old_text": "x", "new_text": "y"})["error"]
    assert "found 0" in ws.run("workspace_edit", {"path": "a.md", "old_text": "z", "new_text": "y"})["error"]
    assert "No file" in ws.run("workspace_edit", {"path": "b.md", "old_text": "z", "new_text": "y"})["error"]


def test_every_change_is_logged_with_a_diff(ws):
    ws.run("workspace_write", {"path": AGENDA_FILE, "content": "## Threads\n- tides\n"}, "s1")
    ws.run("workspace_edit", {"path": AGENDA_FILE, "old_text": "- tides", "new_text": "- tides (paused)"}, "s2")
    ws.run("workspace_read", {"path": AGENDA_FILE}, "s2")
    changes = ws.changes()
    assert [(c["session"], c["tool"], c["created"]) for c in changes] == [
        ("s1", "workspace_write", True), ("s2", "workspace_edit", False)]
    assert "-- tides\n" in changes[1]["diff"] and "+- tides (paused)" in changes[1]["diff"]
    assert ws.changes(path="other.md") == []


def test_agenda_section_when_empty_and_when_kept(ws):
    empty = ws.agenda_section()
    assert "I don't have an agenda yet" in empty and AGENDA_FILE in empty
    assert not (ws.root / AGENDA_FILE).exists(), "nobody starts it for her"
    ws.run("workspace_write", {"path": AGENDA_FILE, "content": "## Waiting on\n- Kohl, on the memory plan\n"})
    kept = ws.agenda_section()
    assert kept.startswith("## MY AGENDA") and "Kohl, on the memory plan" in kept


def test_a_long_agenda_is_capped_in_the_prompt_not_on_disk(ws):
    ws.run("workspace_write", {"path": AGENDA_FILE, "content": "x" * 20_000})
    section = ws.agenda_section()
    assert len(section) < 9_000 and "the rest is in AGENDA.md" in section
    assert len(ws.agenda()) == 20_000


def test_agenda_is_in_the_assembled_prompt_and_never_cut(ws, monkeypatch):
    pytest.importorskip("anthropic")
    from agent_loop.assemble import assemble
    from agent_loop.spec import Trigger
    ws.run("workspace_write", {"path": AGENDA_FILE, "content": "- the memory battery"})
    spec = session_spec("reflection")
    prompt = assemble(spec, Trigger(source="schedule", why="test"), spec.tool_names(), workspace=ws)
    agenda = prompt.section("agenda")
    assert agenda is not None and agenda.never_cut and "the memory battery" in prompt.text
    names = [s.name for s in prompt.sections]
    assert names.index("seam") < names.index("agenda")
