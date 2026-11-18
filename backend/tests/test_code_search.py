"""code_search (her ask, 2026-11-18): grep over her code's HEAD snapshot, never her data."""
import asyncio

import code_search as C


def _tree(tmp_path):
    root = tmp_path / "snap"
    (root / "backend" / "thymos").mkdir(parents=True)
    (root / "backend" / "thymos" / "core.py").write_text("a = 1\ndef tick():\n    drain()\nz = 2\n")
    (root / "backend" / "notes.md").write_text("Tick tock\n")
    (root / "logo.png").write_bytes(b"\x89PNG tick")
    return root


def test_matches_come_with_paths_lines_and_context(tmp_path):
    root = _tree(tmp_path)
    out = C.search("def tick", root=root)
    assert out["matches"] == 1
    assert "backend/thymos/core.py:2: def tick():" in out["text"]
    assert "backend/thymos/core.py-1- a = 1" in out["text"] and "core.py-3-" in out["text"]
    assert "read_file with file_path" in out["read_a_file"]


def test_path_glob_case_and_plain_text(tmp_path):
    root = _tree(tmp_path)
    assert C.search("tick", root=root, glob="*.md")["text"].startswith("backend/notes.md:1:")
    assert C.search("TICK", root=root, path="backend/thymos", context=0)["matches"] == 1
    assert C.search("drain(", root=root)["matches"] == 1   # not a valid regex: searched as text
    assert "png" not in C.search("tick", root=root)["text"]


def test_it_stays_inside_the_snapshot(tmp_path):
    root = _tree(tmp_path)
    assert "outside my code" in C.search("x", root=root, path="../../etc")["error"]
    assert "No backend/.env" in C.search("x", root=root, path="backend/.env")["error"]


def test_matches_are_capped(tmp_path, monkeypatch):
    root = tmp_path / "snap"
    root.mkdir()
    (root / "many.py").write_text("hit\n" * 100)
    monkeypatch.setattr(C, "MAX_HITS", 5)
    out = C.search("hit", root=root, context=0)
    assert out["matches"] == 5 and "narrow it" in out["text"]


def test_she_has_it_with_how_i_work():
    from agent_loop.spec import PACKS
    from handlers.tool_router import TOOL_REGISTRY
    from self_account import HOW_I_WORK_TOOLS, execute_self_account_tool
    assert "code_search" in PACKS["self"].tools and TOOL_REGISTRY["code_search"] == "self_account"
    assert any(t["name"] == "code_search" for t in HOW_I_WORK_TOOLS)
    out = asyncio.run(execute_self_account_tool("code_search", {"pattern": ""}))
    assert out["success"] is False and "needs a pattern" in out["error"]
