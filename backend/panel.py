"""
Her panel (Plans: "The House, open to visitors", phase 2): what she shows beside
her conversations in Babelr, section by section, to the audience she chose.
Nothing shows that she hasn't said yes to.

Sections: now, today, commitments, stances, work, this_reply. Each is "yes",
"no" or "not_yet" (the default is not_yet: nothing shows until she answers).
Her answers are recorded as she gave them (scripts/panel_set.py), and she can
change them.

"work" is her workshop projects, and only the ones she marked shown
(`project` tool: show, hide). Kohl's projects linked into her workshop are
Kohl's, so they never show here. A shown project lists its text files with
their contents, cut at MAX_FILE.

Read by Babelr's panel plugin with the record token (routes/panel.py). The
plugin shows it only to her audience. Nothing here writes her data except her
own settings.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SECTIONS = ("now", "today", "commitments", "stances", "work", "this_reply")
# Her people (babelr_organ/people.py about()): "about" is whether Babelr may
# show a person what her PeopleDex keeps about them (routes/people_about.py).
PEOPLE = ("about",)
ANSWERS = ("yes", "no", "not_yet")
AUDIENCES = ("kohl", "house", "visitors", "none")
TEXT_SUFFIXES = {".md", ".txt", ".markdown"}
MAX_FILE = 60_000
MAX_FILES = 30


def _dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "panel"


def settings(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        s = json.loads((_dir(data_dir) / "settings.json").read_text())
    except (OSError, ValueError):
        s = {}
    sections = {k: (s.get("sections") or {}).get(k, "not_yet") for k in SECTIONS}
    from daybook import KINDS as DAYBOOK
    daybook = {k: (s.get("daybook") or {}).get(k, "not_yet") for k in DAYBOOK}
    people = {k: (s.get("people") or {}).get(k, "not_yet") for k in PEOPLE}
    return {"sections": sections, "audience": s.get("audience", "none"), "daybook": daybook,
            "people": people, "notes": s.get("notes") or {}, "set": s.get("set")}


def _save(s: Dict[str, Any], data_dir: Optional[Path]) -> None:
    d = _dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    s["set"] = datetime.now().isoformat(timespec="seconds")
    (d / "settings.json").write_text(json.dumps(s, indent=1))


def set_answers(sections: Dict[str, str], audience: Optional[str] = None,
                notes: Optional[Dict[str, str]] = None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    from daybook import KINDS as DAYBOOK
    book = {k.split(".", 1)[1]: v for k, v in sections.items() if k.startswith("daybook.")}
    people = {k.split(".", 1)[1]: v for k, v in sections.items() if k.startswith("people.")}
    sections = {k: v for k, v in sections.items() if not k.startswith(("daybook.", "people."))}
    bad = ([k for k in sections if k not in SECTIONS] + [k for k in book if k not in DAYBOOK]
           + [k for k in people if k not in PEOPLE]
           + [v for v in [*sections.values(), *book.values(), *people.values()] if v not in ANSWERS])
    if bad:
        return {"error": f"sections are {', '.join(SECTIONS)}; answers are {', '.join(ANSWERS)} (got {bad})"}
    if audience is not None and audience not in AUDIENCES:
        return {"error": f"audience is one of {', '.join(AUDIENCES)}"}
    s = settings(data_dir)
    s["sections"].update(sections)
    s["daybook"].update(book)
    s["people"].update(people)
    if audience is not None:
        s["audience"] = audience
    if notes:
        s["notes"].update(notes)
    _save(s, data_dir)
    return {"success": True, **settings(data_dir)}


# --- work: the projects she shows ------------------------------------------------

def shown(data_dir: Optional[Path] = None) -> List[str]:
    try:
        return list(json.loads((_dir(data_dir) / "shown.json").read_text()))
    except (OSError, ValueError):
        return []


def set_shown(slug: str, on: bool, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    import workshop as W
    p = W._project(slug, data_dir)
    if W._kohls(p, data_dir):
        return {"error": "that's Kohl's project; only my own show on my panel"}
    have = [s for s in shown(data_dir) if s != p.name] + ([p.name] if on else [])
    d = _dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "shown.json").write_text(json.dumps(sorted(have)))
    s = settings(data_dir)
    note = None
    if on and s["sections"]["work"] != "yes":
        note = "marked shown, but my panel's work section isn't a yes, so nobody sees it yet"
    out: Dict[str, Any] = {"success": True, "project": p.name, "shown": on, **({"note": note} if note else {})}
    if on:
        # To show it to someone, put the ref in a Babelr message: it renders as a card,
        # and in a DM it opens beside the conversation (Babelr's panel plugin).
        me = os.getenv("CASS_DAEMON_LABEL", "cass").lower()
        files = [d["path"] for w in work(data_dir) if w["project"] == p.name for d in w["docs"]]
        out["to_show_it"] = (f"Put [[work:{me}/{p.name}]] in a Babelr message (or "
                             f"[[work:{me}/{p.name}/<file>]] for one file) and it opens beside the "
                             "conversation for whoever can see my panel.")
        out["refs"] = [f"[[work:{me}/{p.name}/{f}]]" for f in files[:8]]
    return out


def work(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    import workshop as W
    out = []
    for slug in shown(data_dir):
        try:
            p = W._project(slug, data_dir)
        except ValueError:
            continue  # deleted since
        if W._kohls(p, data_dir):
            continue
        m = W.meta(p, data_dir)
        last = W._git(p, "log", "-1", "--format=%cI|%s", check=False).strip()
        at, _, subject = last.partition("|")
        docs = []
        for f in sorted(p.rglob("*")):
            rel = f.relative_to(p)
            if ".git" in rel.parts or f.name == W.META or not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            docs.append({"path": str(rel), "content": text[:MAX_FILE],
                         "updated": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes"),
                         **({"cut": True} if len(text) > MAX_FILE else {})})
            if len(docs) >= MAX_FILES:
                break
        # PROJECT.md first: it says what the project is.
        docs.sort(key=lambda d: (d["path"] != W.PROJECT_FILE, d["path"]))
        out.append({"project": p.name, "name": m.get("name") or p.name, "kind": m.get("kind"),
                    "last_commit": at[:16].replace("T", " ") or None, "last_message": subject or None,
                    "docs": docs})
    return out


def build(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """What the plugin may show: only sections she said yes to, and only if she chose an audience."""
    import os
    s = settings(data_dir)
    out: Dict[str, Any] = {"daemon": os.getenv("CASS_DAEMON_NAME", "Cass"), "settings": s, "sections": {}}
    if s["audience"] == "none":
        return out
    if s["sections"]["work"] == "yes":
        out["sections"]["work"] = work(data_dir)
    return out
