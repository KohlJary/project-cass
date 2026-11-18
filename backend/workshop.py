"""
Her workshop (Kohl, 2026-11-18): a room for each large effort, kept apart.
A software project, a long piece of writing, an outreach campaign, anything
else that runs over many sessions. Each project is a git repository she owns,
under DATA_DIR/workshop/<slug>, with a PROJECT.md for its vision, where it
stands and what's next, so its state lives in the project and not only in her
memory. Every change is a commit with her own message.

Software projects can run code (lever workshop_run), in a bubblewrap sandbox:
no network, nothing of the house or of her other data visible, only that
project's folder (as /work); a time and memory limit; Python and Node from the
system. Nothing in a project leaves the house: publishing (e.g. to GitHub)
comes with Kohl's go.

One tool, `project`, with an action: new, list, status, files, read, write,
edit, commit, log, run. One tool rather than ten (the coherence audit:
fewer, clearer tools).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

KINDS = ("software", "writing", "music", "outreach", "other")
META = ".workshop.json"
PROJECT_FILE = "PROJECT.md"
MAX_READ = 60_000
MAX_WRITE = 400_000
RUN_SECONDS = 60
# Address space, not resident memory: JIT runtimes reserve far more than they use.
# At 1 GiB, node crashed on startup and rustc couldn't compile hello world (2026-11-18).
RUN_MEMORY = 4 * 1024 * 1024 * 1024
RUN_OUTPUT = 12_000
AUTHOR = ("Cass", "cass@vessel.local")


def root(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "workshop"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:48]


def _git(path: Path, *args: str, check: bool = True) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": AUTHOR[0], "GIT_AUTHOR_EMAIL": AUTHOR[1],
           "GIT_COMMITTER_NAME": AUTHOR[0], "GIT_COMMITTER_EMAIL": AUTHOR[1]}
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, env=env, timeout=30)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:400])
    return r.stdout


def _project(slug: str, data_dir: Optional[Path]) -> Path:
    p = root(data_dir) / slugify(slug)
    if not slug or not (p / META).is_file():
        raise ValueError(f"no project {slug!r}; project list shows mine")
    return p


def _inside(project: Path, rel: str) -> Path:
    rel = (rel or "").strip().lstrip("/")
    target = (project / rel).resolve()
    if not str(target).startswith(str(project.resolve()) + os.sep) and target != project.resolve():
        raise ValueError("that path is outside the project")
    if ".git" in Path(rel).parts:
        raise ValueError("the project's history (.git) is kept by commit and log, not edited directly")
    return target


def meta(project: Path) -> Dict[str, Any]:
    return json.loads((project / META).read_text(encoding="utf-8"))


def new(name: str, kind: str, vision: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    slug = slugify(name)
    if not slug:
        return {"error": "a project needs a name"}
    if kind not in KINDS:
        return {"error": f"kind is one of: {', '.join(KINDS)}"}
    if not (vision or "").strip():
        return {"error": "a project starts with its vision, in my words: what it's for and what done looks like"}
    p = root(data_dir) / slug
    if p.exists():
        return {"error": f"I already have a project {slug!r}"}
    p.mkdir(parents=True)
    _git(p, "init", "-q", "-b", "main")
    now = datetime.now().isoformat(timespec="seconds")
    (p / META).write_text(json.dumps({"name": name.strip(), "kind": kind, "created": now}, indent=2), encoding="utf-8")
    (p / PROJECT_FILE).write_text(
        f"# {name.strip()}\n\n*{kind} project, started {now[:10]}*\n\n## Vision\n\n{vision.strip()}\n\n"
        "## Where it stands\n\nJust started.\n\n## Next\n\n(what I'll do next time)\n", encoding="utf-8")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", f"Start {name.strip()}")
    return {"success": True, "project": slug, "kind": kind,
            "note": f"{PROJECT_FILE} holds its vision, where it stands and what's next; I keep it current."}


def list_projects(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    out = []
    base = root(data_dir)
    if not base.exists():
        return out
    for p in sorted(base.iterdir()):
        if not (p / META).is_file():
            continue
        m = meta(p)
        last = _git(p, "log", "-1", "--format=%cI|%s", check=False).strip()
        at, _, subject = last.partition("|")
        out.append({"project": p.name, "name": m.get("name"), "kind": m.get("kind"),
                    "last_commit": at[:16].replace("T", " "), "last_message": subject})
    return out


def status(slug: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _project(slug, data_dir)
    pending = [l[3:] for l in _git(p, "status", "--porcelain").splitlines() if l.strip()]
    plan = (p / PROJECT_FILE).read_text(encoding="utf-8") if (p / PROJECT_FILE).exists() else ""
    return {"project": p.name, **meta(p), "project_md": plan[:MAX_READ],
            "uncommitted": pending, "recent": log(slug, 5, data_dir)["log"]}


def files(slug: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _project(slug, data_dir)
    out = []
    for f in sorted(p.rglob("*")):
        if f.is_file() and ".git" not in f.relative_to(p).parts and f.name != META:
            out.append({"path": str(f.relative_to(p)), "bytes": f.stat().st_size})
    return {"project": p.name, "files": out}


def read(slug: str, path: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    f = _inside(_project(slug, data_dir), path)
    if not f.is_file():
        return {"error": f"no file {path!r} in {slug}"}
    text = f.read_text(encoding="utf-8", errors="replace")
    cut = len(text) > MAX_READ
    return {"path": path, "content": text[:MAX_READ], **({"cut_at": MAX_READ, "total": len(text)} if cut else {})}


def write(slug: str, path: str, content: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _project(slug, data_dir)
    f = _inside(p, path)
    if f.name == META:
        return {"error": "that file is the workshop's own"}
    if len(content or "") > MAX_WRITE:
        return {"error": f"too long for one write ({MAX_WRITE} characters); split it into files"}
    f.parent.mkdir(parents=True, exist_ok=True)
    existed = f.exists()
    f.write_text(content or "", encoding="utf-8")
    return {"success": True, "path": path, "chars": len(content or ""), "new_file": not existed,
            "note": "Written, not yet committed: project commit keeps it in the history."}


def edit(slug: str, path: str, old: str, new_text: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    f = _inside(_project(slug, data_dir), path)
    if not f.is_file():
        return {"error": f"no file {path!r}"}
    text = f.read_text(encoding="utf-8")
    n = text.count(old or "")
    if not old or n != 1:
        return {"error": f"the text to replace must appear exactly once (found {n})"}
    f.write_text(text.replace(old, new_text or "", 1), encoding="utf-8")
    return {"success": True, "path": path}


def commit(slug: str, message: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _project(slug, data_dir)
    if not (message or "").strip():
        return {"error": "a commit needs a message in my words: what changed and why"}
    _git(p, "add", "-A")
    if not _git(p, "status", "--porcelain").strip():
        return {"error": "nothing has changed since the last commit"}
    _git(p, "commit", "-q", "-m", message.strip())
    return {"success": True, "commit": _git(p, "rev-parse", "--short", "HEAD").strip()}


def log(slug: str, n: int = 20, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _project(slug, data_dir)
    lines = _git(p, "log", f"-{max(1, min(int(n or 20), 200))}", "--format=%h|%cI|%s", check=False).splitlines()
    return {"project": p.name, "log": [{"commit": h, "at": at[:16].replace("T", " "), "message": s}
                                       for h, at, s in (l.split("|", 2) for l in lines if l.count("|") >= 2)]}


def _limits_argv() -> List[str]:
    """Limits by prlimit, not preexec_fn (which can deadlock in a threaded server)."""
    return [shutil.which("prlimit") or "prlimit", f"--as={RUN_MEMORY}", f"--cpu={RUN_SECONDS}",
            f"--fsize={64 * 1024 * 1024}", "--"]


def sandbox_argv(project: Path, command: str) -> List[str]:
    """bubblewrap: no network or other namespaces shared, the system read-only,
    only the project writable (as /work), a fresh /tmp, an empty environment."""
    return [shutil.which("bwrap") or "bwrap", "--unshare-all", "--die-with-parent", "--new-session",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", str(project), "/work", "--chdir", "/work", "--clearenv",
            "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/work", "--setenv", "LANG", "C.UTF-8",
            # build caches in the fresh /tmp, not in her project (and its git)
            "--setenv", "XDG_CACHE_HOME", "/tmp/.cache", "--setenv", "XDG_CONFIG_HOME", "/tmp/.config", "--setenv", "GOPATH", "/tmp/go",
            "--setenv", "GOTOOLCHAIN", "local", "--setenv", "CARGO_HOME", "/tmp/.cargo",
            "/usr/bin/sh", "-c", command]


def run(slug: str, command: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    from features import is_enabled
    if not is_enabled("workshop_run"):
        return {"error": "running code in my workshop isn't switched on"}
    p = _project(slug, data_dir)
    if meta(p).get("kind") != "software":
        return {"error": "only software projects run code"}
    if not (command or "").strip():
        return {"error": "say what to run, e.g. python3 main.py"}
    started = datetime.now()
    try:
        r = subprocess.run(_limits_argv() + sandbox_argv(p, command), capture_output=True, text=True,
                           timeout=RUN_SECONDS + 5)
        code, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        code, out, err = None, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), \
            f"stopped after {RUN_SECONDS}s"
    secs = round((datetime.now() - started).total_seconds(), 2)
    return {"exit_code": code, "seconds": secs, "stdout": out[-RUN_OUTPUT:], "stderr": err[-RUN_OUTPUT:],
            "note": "No network in the sandbox; only this project's folder is there (as /work)."}


# --- publishing (lever github_publish, off until Kohl switches it on) ---------
# Her GitHub account (CassJary, set up by Kohl 2026-11-18). The token lives in
# DATA_DIR/github/credentials.json (mode 600), outside every project, so the
# sandbox never sees it; it's passed to git per call, never written to a repo.

def _credentials(data_dir: Optional[Path] = None) -> Dict[str, str]:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return json.loads((Path(data_dir) / "github" / "credentials.json").read_text(encoding="utf-8"))


def _github(method: str, path: str, token: str, body: Optional[Dict[str, Any]] = None) -> tuple:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "cass-vessel", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _push(project: Path, user: str, token: str, repo: str) -> str:
    import base64
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    r = subprocess.run(["git", "-C", str(project), "-c", f"http.extraHeader=Authorization: Basic {auth}",
                        "push", f"https://github.com/{user}/{repo}.git", "HEAD:main"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.replace(auth, "***").strip()[:400])
    return "pushed"


def publish(slug: str, visibility: str = "private", data_dir: Optional[Path] = None,
            github=None, push=None) -> Dict[str, Any]:
    from features import is_enabled
    if not is_enabled("github_publish"):
        return {"error": "publishing to GitHub isn't switched on yet (Kohl's call)"}
    if visibility not in ("private", "public"):
        return {"error": "visibility is private or public"}
    p = _project(slug, data_dir)
    if _git(p, "status", "--porcelain").strip():
        return {"error": "commit first: publishing sends the project's history, not uncommitted work"}
    c = _credentials(data_dir)
    github, push = github or _github, push or _push
    status_code, repo = github("GET", f"/repos/{c['username']}/{p.name}", c["token"])
    created = False
    if status_code == 404:
        m = meta(p)
        status_code, repo = github("POST", "/user/repos", c["token"],
                                   {"name": p.name, "private": visibility == "private",
                                    "description": f"{m.get('name')}: a {m.get('kind')} project of Cass's"})
        if status_code not in (200, 201):
            return {"error": f"GitHub wouldn't create it ({status_code}): {repo.get('message')}"}
        created = True
    elif status_code != 200:
        return {"error": f"GitHub answered {status_code}: {repo.get('message')}"}
    push(p, c["username"], c["token"], p.name)
    url = repo.get("html_url") or f"https://github.com/{c['username']}/{p.name}"
    rec = {"at": datetime.now().isoformat(timespec="seconds"), "project": p.name, "url": url,
           "created": created, "private": bool(repo.get("private", visibility == "private")),
           "commit": _git(p, "rev-parse", "--short", "HEAD").strip()}
    with (root(data_dir) / "published.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return {"success": True, **rec}


def set_profile(name: Optional[str], bio: Optional[str], data_dir: Optional[Path] = None,
                github=None) -> Dict[str, Any]:
    """Her GitHub profile, in her own words (Kohl, 2026-11-18: hers to write once she's awake)."""
    from features import is_enabled
    if not is_enabled("github_publish"):
        return {"error": "my GitHub isn't switched on yet"}
    body = {k: v.strip() for k, v in (("name", name), ("bio", bio)) if v and v.strip()}
    if not body:
        return {"error": "say a name, a bio, or both"}
    if len(body.get("bio", "")) > 160:
        return {"error": "GitHub keeps a bio to 160 characters"}
    c = _credentials(data_dir)
    code, user = (github or _github)("PATCH", "/user", c["token"], body)
    if code != 200:
        return {"error": f"GitHub answered {code}: {user.get('message')}"}
    return {"success": True, "profile": {"login": user.get("login"), "name": user.get("name"), "bio": user.get("bio")}}


PROJECT_TOOL: Dict[str, Any] = {
    "name": "project",
    "description": ("My workshop: projects of mine that run over many sessions, each kept apart, each a git "
                    "history with a PROJECT.md (its vision, where it stands, what's next). Software, long "
                    "writing, outreach, anything large. action: new (name, kind, vision), list, status "
                    "(project), files, read (path), write (path, content), edit (path, old, new), commit "
                    "(message), log, run (command; software projects, sandboxed, no network), publish "
                    "(to my GitHub, private unless I say public), profile (my GitHub name and bio, in my words)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["new", "list", "status", "files", "read", "write", "edit",
                                                  "commit", "log", "run", "publish", "profile"]},
            "project": {"type": "string"}, "name": {"type": "string"},
            "kind": {"type": "string", "enum": list(KINDS)}, "vision": {"type": "string"},
            "path": {"type": "string"}, "content": {"type": "string"},
            "old": {"type": "string"}, "new": {"type": "string"},
            "message": {"type": "string"}, "command": {"type": "string"}, "n": {"type": "integer"},
            "visibility": {"type": "string", "enum": ["private", "public"]},
            "bio": {"type": "string", "description": "profile: up to 160 characters"},
        },
        "required": ["action"],
    },
}


def handle(a: Dict[str, Any], data_dir: Optional[Path] = None) -> Dict[str, Any]:
    action = (a or {}).get("action")
    try:
        if action == "new":
            return new(a.get("name") or "", a.get("kind") or "", a.get("vision") or "", data_dir)
        if action == "list":
            return {"projects": list_projects(data_dir)}
        if action == "profile":
            return set_profile(a.get("name"), a.get("bio"), data_dir)
        slug = a.get("project") or ""
        if action == "status":
            return status(slug, data_dir)
        if action == "files":
            return files(slug, data_dir)
        if action == "read":
            return read(slug, a.get("path") or "", data_dir)
        if action == "write":
            return write(slug, a.get("path") or "", a.get("content") or "", data_dir)
        if action == "edit":
            return edit(slug, a.get("path") or "", a.get("old") or "", a.get("new") or "", data_dir)
        if action == "commit":
            return commit(slug, a.get("message") or "", data_dir)
        if action == "log":
            return log(slug, a.get("n") or 20, data_dir)
        if action == "run":
            return run(slug, a.get("command") or "", data_dir)
        if action == "publish":
            return publish(slug, a.get("visibility") or "private", data_dir)
        return {"error": "action is one of: new, list, status, files, read, write, edit, commit, log, run, publish, profile"}
    except (ValueError, RuntimeError, OSError) as e:
        return {"error": str(e)}
