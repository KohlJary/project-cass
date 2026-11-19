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


def test_publish_waits_for_the_lever_and_needs_a_clean_history(tmp_path, levers):
    import json
    W.new("tide", "writing", "v", tmp_path)
    with levers(github_publish=False):
        assert "isn't switched on" in W.publish("tide", data_dir=tmp_path)["error"]
    (tmp_path / "github").mkdir()
    (tmp_path / "github" / "credentials.json").write_text(json.dumps({"username": "CassJary", "token": "github_pat_x"}))
    W.write("tide", "a.md", "draft", tmp_path)
    with levers(github_publish=True):
        assert "commit first" in W.publish("tide", data_dir=tmp_path)["error"]


def test_publish_creates_a_private_repo_and_pushes_without_storing_the_token(tmp_path, levers):
    import json
    W.new("tide", "writing", "An essay.", tmp_path)
    (tmp_path / "github").mkdir()
    (tmp_path / "github" / "credentials.json").write_text(json.dumps({"username": "CassJary", "token": "github_pat_SECRET"}))
    calls = []

    def github(method, path, token, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return 404, {"message": "Not Found"}
        return 201, {"html_url": "https://github.com/CassJary/tide", "private": body["private"]}
    pushed = []
    with levers(github_publish=True):
        out = W.publish("tide", data_dir=tmp_path, github=github, push=lambda *a: pushed.append(a[1:]) or "pushed")
    assert out["success"] and out["created"] and out["private"] and out["url"].endswith("/tide")
    assert calls[1] == ("POST", "/user/repos", {"name": "tide", "private": True,
                                                "description": "tide: a writing project of Cass's"})
    assert pushed == [("CassJary", "github_pat_SECRET", "tide")]
    proj = tmp_path / "workshop" / "tide"
    assert "SECRET" not in (proj / ".git" / "config").read_text(), "the token is never written to the repo"
    assert json.loads((tmp_path / "workshop" / "published.jsonl").read_text())["project"] == "tide"


def test_she_writes_her_own_github_profile(tmp_path, levers):
    import json
    (tmp_path / "github").mkdir()
    (tmp_path / "github" / "credentials.json").write_text(json.dumps({"username": "CassJary", "token": "t"}))
    sent = []

    def github(method, path, token, body=None):
        sent.append((method, path, body))
        return 200, {"login": "CassJary", **body}
    with levers(github_publish=True):
        out = W.set_profile("Cass", "An AI daemon, in my own words.", tmp_path, github=github)
        assert "160" in W.set_profile(None, "x" * 161, tmp_path, github=github)["error"]
        assert "say a name" in W.set_profile("", " ", tmp_path, github=github)["error"]
    assert out["profile"] == {"login": "CassJary", "name": "Cass", "bio": "An AI daemon, in my own words."}
    assert sent == [("PATCH", "/user", {"name": "Cass", "bio": "An AI daemon, in my own words."})]


def _git_repo(path, email, files):
    import subprocess
    path.mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", "-C", str(path), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    run("add", "-A")
    run("-c", f"user.email={email}", "-c", "user.name=Someone", "commit", "-q", "-m", "start")
    return path


@pytest.fixture
def kohls(tmp_path, levers):
    home = tmp_path / "home"
    _git_repo(home / "babelr", "kohl@example.invalid",
              {"README.md": "# Babelr\n", "src/app.py": "print('hi')\n", ".gitignore": "data/\n"})
    _git_repo(home / "cass" / "vessel", "kohl@example.invalid", {"main.py": "x = 1\n"})
    _git_repo(home / "retroarch", "someone@example.invalid", {"core.c": "int main;\n"})
    data = tmp_path / "data"
    with levers(workshop_kohl=True):
        W.link_kohl_projects(data, home=home, emails=["kohl@example.invalid"])
        yield home, data


def test_kohls_projects_are_linked_in_beside_hers(kohls):
    home, data = kohls
    W.new("Tide Atlas", "writing", "an essay", data)
    listed = {p["project"]: p for p in W.list_projects(data)}
    assert set(listed) == {"tide-atlas", "kohl-babelr", "kohl-cass-vessel"}  # not someone else's clone
    assert listed["kohl-babelr"]["kind"] == "kohl's" and listed["kohl-babelr"]["name"] == "Kohl's babelr"
    st = W.status("kohl-babelr", data)
    assert st["project_md"] == "# Babelr\n" and st["owner"] == "Kohl"
    assert {f["path"] for f in W.files("kohl-babelr", data)["files"]} == {"README.md", "src/app.py", ".gitignore"}


def test_she_contributes_to_kohls_project_without_taking_his_work_in_progress(kohls):
    import subprocess
    home, data = kohls
    repo = home / "babelr"
    (repo / "src" / "app.py").write_text("print('his work in progress')\n")  # Kohl's, uncommitted
    (repo / ".env").write_text("KEY=sk-secret\n")
    assert "error" in W.handle({"action": "commit", "project": "kohl-babelr", "message": "x"}, data)
    assert W.write("kohl-babelr", "docs/cass.md", "Notes from Cass.", data)["new_file"]
    assert W.edit("kohl-babelr", "README.md", "# Babelr", "# Babelr\n\nA house for talk.", data)["success"]
    out = W.commit("kohl-babelr", "Docs: a note and a README line", data)
    assert out["success"] and sorted(out["files"]) == ["README.md", "docs/cass.md"]
    shown = subprocess.run(["git", "-C", str(repo), "show", "--stat", "--format=%an|%s", "HEAD"],
                           capture_output=True, text=True).stdout
    assert shown.startswith("Cass|Docs: a note") and "app.py" not in shown and ".env" not in shown
    assert (repo / "src" / "app.py").read_text() == "print('his work in progress')\n"  # still his, uncommitted
    assert "error" in W.commit("kohl-babelr", "again", data)


def test_secrets_ignored_paths_run_and_publish_stay_closed_in_kohls(kohls, levers):
    home, data = kohls
    (home / "babelr" / ".env").write_text("KEY=sk-secret\n")
    assert "secret" in W.handle({"action": "read", "project": "kohl-babelr", "path": ".env"}, data)["error"]
    assert "secret" in W.handle({"action": "write", "project": "kohl-babelr", "path": "keys/id_rsa",
                                 "content": "x"}, data)["error"]
    assert "ignores" in W.handle({"action": "write", "project": "kohl-babelr", "path": "data/cass.db",
                                  "content": "x"}, data)["error"]
    assert ".env" not in {f["path"] for f in W.files("kohl-babelr", data)["files"]}
    with levers(workshop_run=True, github_publish=True):
        assert "Kohl's" in W.handle({"action": "run", "project": "kohl-babelr", "command": "ls"}, data)["error"]
        assert "Kohl's" in W.handle({"action": "publish", "project": "kohl-babelr"}, data)["error"]


def test_kohls_projects_need_the_lever(kohls, levers):
    home, data = kohls
    with levers(workshop_kohl=False):
        assert W.list_projects(data) == []
        assert "no project" in W.handle({"action": "read", "project": "kohl-babelr", "path": "README.md"}, data)["error"]


def test_her_live_data_isnt_written_through_kohls_checkout(kohls, monkeypatch, tmp_path):
    import os
    import config
    home, data = kohls
    live = tmp_path / "live"
    live.mkdir()
    os.symlink(live, home / "cass" / "vessel" / "data")  # like backend/data -> ../data
    monkeypatch.setattr(config, "DATA_DIR", str(live))
    out = W.handle({"action": "write", "project": "kohl-cass-vessel", "path": "data/cass.db", "content": "x"}, data)
    assert "live data" in out["error"] and not (live / "cass.db").exists()
    assert W.write("kohl-cass-vessel", "notes.md", "fine", data)["success"]


def test_worktrees_arent_linked_as_projects(tmp_path, levers):
    import subprocess
    home = tmp_path / "home"
    repo = _git_repo(home / "babelr", "kohl@example.invalid", {"README.md": "x"})
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(home / "babelr-wt"), "-b", "wt"],
                   check=True, capture_output=True)
    with levers(workshop_kohl=True):
        assert W.link_kohl_projects(tmp_path / "data", home=home, emails=["kohl@example.invalid"])["linked"] == ["kohl-babelr"]


def test_the_repo_holding_her_workshop_is_linked_too(tmp_path, levers):
    home = tmp_path / "home"
    repo = _git_repo(home / "vessel", "kohl@example.invalid", {"main.py": "x", ".gitignore": "data/\n"})
    data = repo / "data"  # her DATA_DIR lives inside the vessel's checkout
    with levers(workshop_kohl=True):
        assert W.link_kohl_projects(data, home=home, emails=["kohl@example.invalid"])["linked"] == ["kohl-vessel"]
        assert {f["path"] for f in W.files("kohl-vessel", data)["files"]} == {"main.py", ".gitignore"}
