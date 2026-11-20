"""
Sharing workshop projects between the daemons of one house (Kohl, 2026-11-20: "give Cass the
ability to share projects in her workspace with Eris").

A house has a shared folder (HOUSE_SHARED_DIR; each vessel sees it at its own path). A daemon
shares one of its own projects by naming who with: the project is pushed there as a bare git
repository, <shared>/<owner>/<slug>.git, beside <slug>.json saying who it's shared with. From
then on her commits sync to it. The one it's shared with sees it in their workshop as
<owner>-<slug>, joins it (a working clone of their own), and their commits sync back. Either
side pulls the other's work with sync. Nothing is shared unless its owner says so, and only
with whom she names; unshare takes it back from them (what they already pulled stays with them).

Vessels run as different users (Cass on the host, a member in a container), so the shared
repositories are made world-writable (git --shared=0777) and git is told to trust them.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

SAFE = ["-c", "safe.directory=*"]


def shared_dir() -> Optional[Path]:
    p = os.getenv("HOUSE_SHARED_DIR")
    return Path(p) if p else None


def me() -> str:
    return os.getenv("CASS_DAEMON_LABEL", "cass")


def _git(path: Path, *args: str, check: bool = True) -> str:
    from workshop import AUTHOR
    env = {**os.environ, "GIT_AUTHOR_NAME": AUTHOR[0], "GIT_AUTHOR_EMAIL": AUTHOR[1],
           "GIT_COMMITTER_NAME": AUTHOR[0], "GIT_COMMITTER_EMAIL": AUTHOR[1]}
    r = subprocess.run(["git", *SAFE, "-C", str(path), *args], capture_output=True, text=True, env=env, timeout=60)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:400])
    return r.stdout


def _need_shared() -> Path:
    d = shared_dir()
    if not d or not d.is_dir():
        raise ValueError("this house has no shared folder for projects (HOUSE_SHARED_DIR)")
    return d


def _manifest_path(owner: str, slug: str) -> Path:
    return _need_shared() / owner / f"{slug}.json"


def _read_manifest(owner: str, slug: str) -> Optional[Dict[str, Any]]:
    p = _manifest_path(owner, slug)
    return json.loads(p.read_text()) if p.exists() else None


def _write_manifest(owner: str, slug: str, m: Dict[str, Any]) -> None:
    p = _manifest_path(owner, slug)
    p.write_text(json.dumps(m, indent=2))
    os.chmod(p, 0o666)


def is_shared_clone(project: Path) -> bool:
    meta = project / ".workshop.json"
    try:
        return json.loads(meta.read_text()).get("kind") == "shared"
    except (OSError, ValueError):
        return False


def has_house_remote(project: Path) -> bool:
    return "house" in _git(project, "remote", check=False).split()


def share(project: Path, slug: str, with_: str, name: str) -> Dict[str, Any]:
    """Share my project `slug` with daemon `with_` (their label)."""
    with_ = (with_ or "").strip().lower()
    if not with_ or with_ == me():
        return {"error": "say who to share it with (another daemon in this house, by name)"}
    d = _need_shared()
    owner_dir = d / me()
    owner_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(owner_dir, 0o777)
    bare = owner_dir / f"{slug}.git"
    if not bare.exists():
        subprocess.run(["git", "init", "-q", "--bare", "--shared=0777", "-b", "main", str(bare)], check=True,
                       capture_output=True)
    if not has_house_remote(project):
        _git(project, "remote", "add", "house", str(bare))
    _git(project, "push", "-q", "house", "HEAD:main")
    m = _read_manifest(me(), slug) or {"from": me(), "project": slug, "name": name, "with": []}
    if with_ not in m["with"]:
        m["with"].append(with_)
    _write_manifest(me(), slug, m)
    return {"success": True, "shared_with": m["with"],
            "note": f"{with_} sees it as {me()}-{slug}; my commits here sync to it, and sync pulls theirs"}


def unshare(slug: str, with_: str) -> Dict[str, Any]:
    m = _read_manifest(me(), slug)
    if not m:
        return {"error": f"{slug} isn't shared"}
    m["with"] = [w for w in m["with"] if w != (with_ or "").strip().lower()]
    _write_manifest(me(), slug, m)
    return {"success": True, "shared_with": m["with"],
            "note": "they can't sync it any more; what they already pulled stays with them"}


def offered_to_me() -> List[Dict[str, Any]]:
    """Projects other daemons in this house have shared with me."""
    d = shared_dir()
    if not d or not d.is_dir():
        return []
    out = []
    for mf in sorted(d.glob("*/*.json")):
        try:
            m = json.loads(mf.read_text())
        except (OSError, ValueError):
            continue
        if me() in m.get("with", []) and m.get("from") != me():
            out.append({"project": f"{m['from']}-{m['project']}", "name": m.get("name"), "from": m["from"]})
    return out


def join(workshop_root: Path, project: str) -> Dict[str, Any]:
    """Take a working copy of a project shared with me, as <owner>-<slug>."""
    offer = next((o for o in offered_to_me() if o["project"] == project), None)
    if not offer:
        return {"error": f"nothing called {project!r} is shared with me; project list shows what is"}
    owner, slug = offer["from"], project[len(offer["from"]) + 1:]
    dest = workshop_root / project
    if dest.exists():
        return {"error": f"I already have {project}; sync pulls the latest"}
    workshop_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", *SAFE, "clone", "-q", "-o", "house", str(_need_shared() / owner / f"{slug}.git"),
                    str(dest)], check=True, capture_output=True)
    (dest / ".workshop.json").write_text(json.dumps({"name": offer.get("name") or slug, "kind": "shared",
                                                     "owner": owner}, indent=2))
    excl = dest / ".git" / "info" / "exclude"
    excl.write_text(excl.read_text() + "\n.workshop.json\n" if excl.exists() else ".workshop.json\n")
    return {"success": True, "project": project, "note": f"{owner}'s project, shared with me; commit syncs back"}


def _allowed(project: Path) -> bool:
    """Am I still allowed to sync this? Owners always; a shared clone while it's shared with me."""
    if not is_shared_clone(project):
        return True
    owner = json.loads((project / ".workshop.json").read_text())["owner"]
    m = _read_manifest(owner, project.name[len(owner) + 1:])
    return bool(m and me() in m.get("with", []))


def sync(project: Path) -> Dict[str, Any]:
    if not has_house_remote(project):
        return {"error": "this project isn't shared; share it first"}
    if not _allowed(project):
        return {"error": "it isn't shared with me any more"}
    _git(project, "pull", "-q", "--rebase", "house", "main")
    _git(project, "push", "-q", "house", "HEAD:main")
    return {"success": True, "head": _git(project, "log", "-1", "--format=%h %an: %s").strip()}


def after_commit(project: Path) -> Optional[str]:
    """After a commit in a shared project: pull theirs, push mine. Returns a note, or None."""
    if not has_house_remote(project):
        return None
    try:
        return "synced with the house copy: " + sync(project).get("head", "")
    except (RuntimeError, ValueError) as e:
        return f"committed here, but the house copy didn't sync: {e}"
