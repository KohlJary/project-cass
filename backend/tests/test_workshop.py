"""Her workshop (workshop.py): projects as git repos she owns, kept apart; code
runs only for software projects, sandboxed with no network and nothing else visible."""
import shutil

import pytest

import workshop as W


def test_a_project_starts_with_its_vision_and_keeps_a_history(tmp_path):
    assert "vision" in W.new("Tide Atlas", "writing", "", tmp_path)["error"]
    assert "kind is one of" in W.new("x", "novel", "v", tmp_path)["error"]
    out = W.new("Tide Atlas", "writing", "A long essay on what tides teach about patience.", tmp_path)
    assert out["project"] == "tide-atlas"
    assert "already have" in W.new("Tide Atlas", "writing", "again", tmp_path)["error"]
    st = W.status("tide-atlas", tmp_path)
    assert "## Vision\n\nA long essay on what tides teach" in st["project_md"] and st["kind"] == "writing"
    assert W.write("tide-atlas", "chapters/one.md", "The moon pulls.", tmp_path)["new_file"]
    assert W.edit("tide-atlas", "chapters/one.md", "pulls", "pulls, and I listen", tmp_path)["success"]
    assert "nothing has changed" not in str(W.commit("tide-atlas", "First chapter, first line", tmp_path))
    assert "nothing has changed" in W.commit("tide-atlas", "again", tmp_path)["error"]
    assert [e["message"] for e in W.log("tide-atlas", 5, tmp_path)["log"]] == ["First chapter, first line", "Start Tide Atlas"]
    assert W.read("tide-atlas", "chapters/one.md", tmp_path)["content"] == "The moon pulls, and I listen."
    assert [p["project"] for p in W.list_projects(tmp_path)] == ["tide-atlas"]


def test_paths_stay_inside_the_project_and_history_isnt_edited(tmp_path):
    W.new("a", "other", "v", tmp_path)
    W.new("b", "other", "v", tmp_path)
    for bad in ("../b/PROJECT.md", ".git/config"):
        assert "error" in W.handle({"action": "write", "project": "a", "path": bad, "content": "x"}, tmp_path), bad
    # An absolute path is taken as inside the project, never the real one.
    W.handle({"action": "write", "project": "a", "path": "/etc/passwd", "content": "x"}, tmp_path)
    assert (tmp_path / "workshop" / "a" / "etc" / "passwd").read_text() == "x"
    assert "error" in W.handle({"action": "read", "project": "a", "path": "../../.."}, tmp_path)
    assert "error" in W.handle({"action": "write", "project": "a", "path": W.META, "content": "{}"}, tmp_path)


def test_only_software_projects_run_and_only_with_the_lever(tmp_path, levers):
    W.new("essay", "writing", "v", tmp_path)
    with levers(workshop_run=True):
        assert "only software" in W.run("essay", "echo hi", tmp_path)["error"]
    W.new("tool", "software", "v", tmp_path)
    with levers(workshop_run=False):
        assert "isn't switched on" in W.run("tool", "echo hi", tmp_path)["error"]


@pytest.mark.skipif(not (shutil.which("bwrap") and shutil.which("prlimit")), reason="needs bubblewrap and prlimit")
def test_the_sandbox_has_no_network_and_sees_only_the_project(tmp_path, levers):
    W.new("probe", "software", "check the walls", tmp_path)
    W.write("probe", "main.py", "\n".join([
        "import os, socket",
        "print('cwd', os.getcwd(), sorted(os.listdir('.')))",
        "for p in ['/home', '/root', '/etc/passwd']: print(p, os.path.exists(p))",
        "try:",
        "    socket.create_connection(('1.1.1.1', 53), timeout=2); print('net open')",
        "except OSError: print('net blocked')",
        "open('made.txt', 'w').write('kept')"]), tmp_path)
    with levers(workshop_run=True):
        out = W.run("probe", "python3 main.py", tmp_path)
    assert out["exit_code"] == 0, out
    assert "cwd /work" in out["stdout"] and "net blocked" in out["stdout"]
    assert "/home False" in out["stdout"] and "/root False" in out["stdout"]
    assert (tmp_path / "workshop" / "probe" / "made.txt").read_text() == "kept"
