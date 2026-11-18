"""
The record (Kohl, 2026-11-17): one place to see what Cass has planned, asked
for, changed in herself, and done in the world. It's for diagnostics (is
everything working?) and for following her progress, and for any account of
her that has to hold up; Kohl, 2026-11-18: "not intended to be like a
surveillance thing". Kohl reads it in Babelr ("Cass's record"); she reads it
with my_record (self_account.py); her Room stays what she chooses to share.

Because it may be read as evidence, every entry is:
  - dated (`at`, ISO local time);
  - attributed (`who`: "cass", "kohl", or the account that acted; for changes
    made to her code, the commit author; nothing is guessed);
  - sourced (`source`: the Plans event seq, the commit, the log file and line,
    the reach-out id), so it can be checked against where it came from;
  - copied as recorded, not summarized: titles and her words as written,
    long text cut with a marker, never reworded.

It reads; it never writes anything of hers. Sources that can't be read are
named in `unavailable`, not silently left out.

Read with a record token (scripts/record_token.py), separate from her room's.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

TEXT_CAP = 600
KINDS = ("plan", "ask", "change", "code", "world", "day")
KIND_WORDS = {
    "plan": "Her plans",
    "ask": "Her asks",
    "change": "Changes to how she works",
    "code": "Changes to her code",
    "world": "In the world",
    "day": "Her days",
}


def _data_dir(data_dir: Optional[Path]) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    from config import DATA_DIR
    return Path(DATA_DIR)


def _cap(text: Any) -> str:
    s = str(text or "").strip()
    return s if len(s) <= TEXT_CAP else s[:TEXT_CAP] + f" [... {len(s) - TEXT_CAP} more characters]"


def _entry(at: Any, who: str, kind: str, title: str, source: str, detail: str = "") -> Dict[str, Any]:
    return {"at": str(at or ""), "who": who, "kind": kind, "title": _cap(title),
            "detail": _cap(detail), "source": source}


def _jsonl(path: Path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for n, line in enumerate(lines, 1):
        try:
            yield n, json.loads(line)
        except ValueError:
            continue


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def from_changes(dd: Path) -> List[Dict[str, Any]]:
    """What changed in how she works (self_account.py's change feed)."""
    out = []
    path = dd / "self_account" / "changes.jsonl"
    for n, rec in _jsonl(path):
        for change in rec.get("changes") or []:
            out.append(_entry(rec.get("at"), "system", "change", change,
                              f"self_account/changes.jsonl:{n}"))
    return out


def _local(at: Any) -> str:
    """An event time in local time (Plans stores UTC, "…Z"), as the rest of the record."""
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return str(at or "")
    return (t.astimezone().replace(tzinfo=None) if t.tzinfo else t).isoformat(timespec="seconds")


def from_plans(events: List[Dict[str, Any]], her_plans: Dict[str, str],
               me: str = "cass", items: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Plans events on her plans (any actor) and hers anywhere. `her_plans`:
    slug -> title, for plans she created."""
    out = []
    for e in events:
        slug = e.get("planSlug") or ""
        actor = ((e.get("actor") or {}).get("name") or "").lower()
        if slug not in her_plans and actor != me:
            continue
        action = e.get("action") or ""
        if action == "comment":
            continue   # discussion, not a change; it stays in Plans
        d = e.get("detail") or {}
        what = (d.get("title") or d.get("item") or (items or {}).get(e.get("itemId") or "")
                or d.get("phase") or d.get("goal") or "")
        status = d.get("status") or d.get("after") or d.get("to") or ""   # Plans: {"before", "after"}
        plan_title = her_plans.get(slug) or slug
        kind = "ask" if "ask" in slug and slug not in her_plans else "plan"
        if plan_title.lower().startswith("cass's asks"):
            kind = "ask"
        title = f"{action.replace('-', ' ')}: {what}".strip(": ") + (f" -> {status}" if status else "")
        detail = f"in \"{plan_title}\"" + (f"; {d['resolution']}" if d.get("resolution") else "") \
            + (f"; why: {d['why']}" if d.get("why") else "")
        out.append(_entry(_local(e.get("at")), actor or "?", kind, title,
                          f"Plans event #{e.get('seq')} ({slug})", detail))
    return out


def from_reach_outs(rows: List[Any]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        via = ", ".join(sorted({str(v.get("channel")) for v in (r.delivered_via or []) if v.get("ok", True)}))
        out.append(_entry(r.created_at, "cass", "world", f"reached out to Kohl ({r.kind})"
                          + (f" via {via}" if via else ""), f"reach_outs id {r.id}", r.body))
    return out


def from_social(dd: Path) -> List[Dict[str, Any]]:
    out = []
    for platform in ("bluesky", "tumblr"):
        path = dd / "social" / platform / "posted.jsonl"
        for n, rec in _jsonl(path):
            kind = rec.get("kind") or "?"
            target = rec.get("with") or rec.get("to") or rec.get("in_reply_to") or ""
            title = f"{platform}: {kind}" + (f" ({target})" if target else "")
            body = "" if kind == "dm" else rec.get("text")   # DMs: that it happened, not what
            out.append(_entry(rec.get("at"), "cass", "world", title,
                              f"social/{platform}/posted.jsonl:{n}" + (f" {rec['uri']}" if rec.get("uri") else ""),
                              body))
    return out


def from_room(dd: Path) -> List[Dict[str, Any]]:
    try:
        state = json.loads((dd / "room" / "shares.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [_entry(s.get("shared_at"), "cass", "world",
                   f"shared a {s.get('kind')} to her room for {s.get('audience')}: {s.get('title') or s.get('id')}",
                   "room/shares.json", s.get("note")) for s in state.get("shares") or []]


def from_days(dd: Path) -> List[Dict[str, Any]]:
    out = []
    shape_path = dd / "day_plans" / "shape.json"
    try:
        shape = json.loads(shape_path.read_text(encoding="utf-8"))
        out.append(_entry(shape.get("set_at"), "cass", "day",
                          "set her day shape: " + ", ".join(f"{k} {v}" for k, v in (shape.get("shape") or {}).items()),
                          "day_plans/shape.json (current; earlier shapes aren't kept)", shape.get("why")))
    except (OSError, ValueError):
        pass
    try:
        routines = json.loads((dd / "day_plans" / "routines.json").read_text(encoding="utf-8"))
        for r in routines.get("routines") or []:
            out.append(_entry("", "cass", "day",
                              f"routine: {r.get('at')} {','.join(r.get('days') or [])} {r.get('template_id')}",
                              "day_plans/routines.json (current)", r.get("focus")))
    except (OSError, ValueError):
        pass
    for n, rec in _jsonl(dd / "day_plans" / "carried.jsonl"):
        out.append(_entry(rec.get("at"), "cass", "day",
                          f"planned time for \"{rec.get('plan_title')}\": {rec.get('item')}",
                          f"day_plans/carried.jsonl:{n}"))
    return out


def from_git(repo: Path, since: datetime) -> List[Dict[str, Any]]:
    """Commits to the vessel: what was changed in her code, by whom, when.
    The author is the commit's; the subject line as written."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={since.isoformat()}",
             "--pretty=format:%H%x1f%aI%x1f%an%x1f%s"],
            capture_output=True, text=True, timeout=20, check=True).stdout
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"git log failed: {e}")
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            h, at, author, subject = parts
            rows.append(_entry(at, author.lower(), "code", subject, f"commit {h[:12]}"))
    return rows


def spend_by_day(dd: Path, since: datetime) -> List[Dict[str, Any]]:
    """Sessions and their recorded cost per day, from her session logs."""
    from scheduling.day_recap import _sessions
    days: Dict[str, Dict[str, Any]] = {}
    for s in _sessions(dd, since):
        d = days.setdefault(s["at"].strftime("%Y-%m-%d"), {"day": s["at"].strftime("%Y-%m-%d"),
                                                          "sessions": 0, "cost_usd": 0.0, "minutes": 0.0})
        d["sessions"] += 1
        d["cost_usd"] = round(d["cost_usd"] + s["cost"], 4)
        d["minutes"] = round(d["minutes"] + s["seconds"] / 60, 1)
    return sorted(days.values(), key=lambda d: d["day"], reverse=True)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

def _live_plans() -> tuple:
    """(events, {slug: title} of her plans) from Babelr's Plans, as her organ sees them."""
    from babelr_organ.organ import PLANS, get_babelr_organ
    organ = get_babelr_organ()
    if organ is None or not organ.enabled:
        raise RuntimeError("Babelr isn't connected")
    me = (organ.my_username or "cass").lower()
    mine = {r["slug"]: r.get("title") or r["slug"] for r in organ._plan_rows()
            if ((r.get("createdBy") or {}).get("name") or "").lower() == me}
    items: Dict[str, str] = {}   # item id -> title, for events that carry only the id
    for slug in mine:
        for i in (organ.client._req("GET", f"{PLANS}/plans/{slug}") or {}).get("items") or []:
            items[i["id"]] = i.get("title") or ""
    events, after = [], 0
    for _ in range(50):
        page = organ.client._req("GET", f"{PLANS}/events?after={after}") or {}
        batch = page.get("events") or []
        events += batch
        if not batch or page.get("cursor", after) == after:
            break
        after = page["cursor"]
    return events, mine, items


def _live_reach_outs(limit: int = 500) -> List[Any]:
    from reach_out import ReachOutManager, find_primary_partner
    from database import get_daemon_id
    daemon_id = get_daemon_id()   # the id (her_daemon()[0] is the label: it read no reach-outs at all)
    partner = find_primary_partner(daemon_id)
    return ReachOutManager(daemon_id).history(partner, limit=limit) if partner else []


def build(days: int = 30, data_dir: Optional[Path] = None, now: Optional[datetime] = None,
          plans: Optional[Callable[[], tuple]] = None, reach_outs: Optional[Callable[[], List[Any]]] = None,
          repo: Optional[Path] = None) -> Dict[str, Any]:
    """The record for the last `days` days, newest first."""
    now = now or datetime.now()
    since = now - timedelta(days=days)
    dd = _data_dir(data_dir)
    entries: List[Dict[str, Any]] = []
    unavailable: List[str] = []

    def take(name: str, fn: Callable[[], List[Dict[str, Any]]]) -> None:
        try:
            entries.extend(fn())
        except Exception as e:  # named, not hidden
            logger.warning(f"[record] {name} unavailable: {e}")
            unavailable.append(f"{name}: {e}")

    def _plans():
        got = (plans or _live_plans)()
        events, mine = got[0], got[1]
        return from_plans(events, mine, items=got[2] if len(got) > 2 else None)
    take("Plans", _plans)
    take("changes to how she works", lambda: from_changes(dd))
    take("reach-outs", lambda: from_reach_outs((reach_outs or _live_reach_outs)()))
    take("Bluesky/Tumblr", lambda: from_social(dd))
    take("her room", lambda: from_room(dd))
    take("her days", lambda: from_days(dd))
    take("vessel commits", lambda: from_git(repo or Path(__file__).resolve().parent.parent, since))

    def when(e):
        try:
            t = datetime.fromisoformat(e["at"].replace("Z", "+00:00"))
            return t.astimezone().replace(tzinfo=None) if t.tzinfo else t
        except ValueError:
            return None
    kept = [e for e in entries if (when(e) is None or when(e) >= since)]
    kept.sort(key=lambda e: when(e) or now, reverse=True)
    spend = []
    try:
        spend = spend_by_day(dd, since)
    except Exception as e:
        unavailable.append(f"session spend: {e}")
    body = {"generated_at": now.isoformat(timespec="seconds"), "days": days, "entries": kept,
            "spend_by_day": spend, "unavailable": unavailable, "kinds": KIND_WORDS}
    body["digest"] = hashlib.sha256(json.dumps(kept, sort_keys=True).encode()).hexdigest()
    return body


def to_markdown(record: Dict[str, Any]) -> str:
    """The record as Markdown, for a write-up: by kind, newest first, every line sourced."""
    lines = [f"# Cass: the record, last {record['days']} days",
             f"Generated {record['generated_at']}. Entries: {len(record['entries'])}. "
             f"Digest (sha256 of the entries): `{record['digest']}`.", ""]
    if record["unavailable"]:
        lines += ["**Not included (couldn't be read):** " + "; ".join(record["unavailable"]), ""]
    for kind, words in KIND_WORDS.items():
        rows = [e for e in record["entries"] if e["kind"] == kind]
        if not rows:
            continue
        lines += [f"## {words} ({len(rows)})", ""]
        for e in rows:
            line = f"- **{e['at'][:16].replace('T', ' ') or 'undated'}** · {e['who']} · {e['title']}"
            if e["detail"]:
                line += f"  \n  {e['detail']}"
            line += f"  \n  _source: {e['source']}_"
            lines.append(line)
        lines.append("")
    if record["spend_by_day"]:
        lines += ["## Sessions and spend by day", "", "| Day | Sessions | Minutes | Cost (USD) |",
                  "|---|---|---|---|"]
        lines += [f"| {d['day']} | {d['sessions']} | {d['minutes']} | {d['cost_usd']:.2f} |"
                  for d in record["spend_by_day"]]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Tokens (kept apart from her room's: a room token never reads the record)
# ---------------------------------------------------------------------------

def _tokens_path(data_dir: Optional[Path]) -> Path:
    return _data_dir(data_dir) / "record" / "tokens.json"


def mint_token(name: str, data_dir: Optional[Path] = None) -> str:
    token = "record_" + secrets.token_urlsafe(32)
    path = _tokens_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        tokens = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tokens = []
    tokens.append({"hash": hashlib.sha256(token.encode()).hexdigest(), "name": name,
                   "created_at": datetime.now().isoformat(timespec="seconds")})
    path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return token


def token_ok(token: Optional[str], data_dir: Optional[Path] = None) -> bool:
    if not token or not token.startswith("record_"):
        return False
    h = hashlib.sha256(token.encode()).hexdigest()
    try:
        tokens = json.loads(_tokens_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(secrets.compare_digest(t.get("hash", ""), h) for t in tokens)


# ---------------------------------------------------------------------------
# Kohl's end-of-day review (2026-11-18): "come back at the end and review
# everything y'all did". One page: her day, what we built, what's waiting on
# him, what went wrong, what it cost. Every source that can't be read is named.
# ---------------------------------------------------------------------------

REVIEW_REPOS = {"cass-vessel": Path(__file__).resolve().parent.parent,
                "babelr": Path.home() / "babelr", "Chapter-House": Path.home() / "Chapter-House"}


def _waiting_on_kohl() -> List[str]:
    """Phases that wait on Kohl's yes, and her open asks."""
    from babelr_organ.organ import PLANS, get_babelr_organ
    organ = get_babelr_organ()
    if organ is None or not organ.enabled:
        raise RuntimeError("Babelr isn't connected")
    lines = []
    for row in organ._plan_rows():
        d = organ.client._req("GET", f"{PLANS}/plans/{row['slug']}") or {}
        for f in d.get("phases") or []:
            if f.get("status") == "proposed" and any(n.lower() in ("jaryk", "kohl") for n in f.get("awaiting") or []):
                lines.append(f"- Phase waiting on your yes: \"{d.get('title')}\", phase {f.get('position', 0) + 1}: "
                             f"{f.get('title')}")
        if (d.get("title") or "").startswith("Cass's asks"):
            for i in d.get("items") or []:
                if i.get("status") in ("open", "in_progress"):
                    lines.append(f"- Her ask ({i.get('status')}): {i.get('title')}")
    return lines


def _jsonl_since(path: Path, since: datetime) -> List[Dict[str, Any]]:
    out = []
    for _, rec in _jsonl(path):
        try:
            if datetime.fromisoformat(str(rec.get("at"))) >= since:
                out.append(rec)
        except ValueError:
            continue
    return out


def build_review(hours: int = 24, data_dir: Optional[Path] = None, now: Optional[datetime] = None,
                 waiting: Optional[Callable[[], List[str]]] = None,
                 heartbeat: Optional[Callable[[datetime], tuple]] = None,
                 record: Optional[Dict[str, Any]] = None, repos: Optional[Dict[str, Path]] = None) -> str:
    now = now or datetime.now()
    since = now - timedelta(hours=hours)
    dd = _data_dir(data_dir)
    rec = record if record is not None else build(days=max(1, (hours + 23) // 24), data_dir=data_dir, now=now)

    def recent(e):
        try:
            t = datetime.fromisoformat(e["at"].replace("Z", "+00:00"))
            t = t.astimezone().replace(tzinfo=None) if t.tzinfo else t
            return t >= since
        except ValueError:
            return False
    entries = [e for e in rec["entries"] if recent(e)]
    out = [f"# Daily review: {now:%A %Y-%m-%d %H:%M} (last {hours} hours)", ""]
    unreadable = list(rec.get("unavailable") or [])

    def section(title, lines, empty):
        out.extend([f"## {title}", ""] + (lines or [empty]) + [""])

    mine = [e for e in entries if e["kind"] != "code"]
    flat = lambda s, n: " ".join(str(s or "").split())[:n]  # noqa: E731
    section("What Cass did", [f"- {e['at'][11:16]} {KIND_WORDS.get(e['kind'], e['kind'])}: {flat(e['title'], 160)}"
                              + (f": {flat(e['detail'], 200)}" if e['detail'] else "") for e in mine],
            "Nothing recorded.")
    built = []
    for name, path in (repos or REVIEW_REPOS).items():
        try:
            built += [f"- {name}: {e['title']} ({e['who']}, {e['source'].replace('commit ', '')})"
                      for e in from_git(path, since)]
        except Exception as e:
            unreadable.append(f"{name} commits: {e}")
    section("What was built", built, "No commits.")
    made = []   # her own workshop commits (workshop.py), project by project
    try:
        import workshop
        for proj in workshop.list_projects(data_dir):
            for e in from_git(workshop.root(data_dir) / proj["project"], since):
                made.append(f"- {proj['name']} ({proj['kind']}): {e['title']} ({e['at'][11:16]})")
    except Exception as e:
        unreadable.append(f"her workshop: {e}")
    section("What she made in her workshop", made, "No workshop commits.")
    try:
        section("Waiting on you", (waiting or _waiting_on_kohl)(), "Nothing.")
    except Exception as e:
        unreadable.append(f"waiting on you: {e}")
        section("Waiting on you", [], "(couldn't be read; see below)")
    trouble = []
    try:
        if heartbeat is None:
            from heartbeat.runlog import RunLog
            refused, failed = RunLog().refused_since(since), RunLog().failed_since(since)
        else:
            refused, failed = heartbeat(since)
        trouble += [f"- Refused: {r['work_name']} at {str(r['started_at'])[11:16]}: {r.get('error')}" for r in refused]
        trouble += [f"- Failed: {r['work_name']} at {str(r['started_at'])[11:16]}: {(r.get('error') or '')[:160]}"
                    for r in failed]
    except Exception as e:
        unreadable.append(f"Heartbeat runs: {e}")
    labels = _jsonl_since(dd / "social" / "triage.jsonl", since)
    crisis = [r for r in labels if r.get("label") == "crisis"]
    if crisis:
        trouble.append(f"- {len(crisis)} inbound message(s) labeled crisis (social/triage.jsonl): check she answered, "
                       "and whether she flagged you.")
    section("Anything off", trouble, "Nothing refused or failed.")
    notes = [r for r in _jsonl_since(dd / "gremlin" / "reviews.jsonl", since)]
    held = [r for r in notes if r.get("notes")]
    follow = [r for r in notes if r.get("followup")]
    signals = []
    if labels:
        signals.append(f"- Triage labels: {len(labels)} ({', '.join(sorted({str(r.get('label')) for r in labels}))}).")
    if notes:
        signals.append(f"- Gremlin reviews: {len(notes)} drafts, {len(held)} got notes, "
                       f"{sum(1 for r in follow if r.get('revised'))} of {len(follow)} follow-ups revised.")
    section("Signals", signals, "None.")
    today = [d for d in rec.get("spend_by_day") or [] if d["day"] >= since.strftime("%Y-%m-%d")]
    section("Spend", [f"- {d['day']}: {d['sessions']} sessions, {d['minutes']} min, ${d['cost_usd']:.2f}" for d in today],
            "No sessions.")
    if unreadable:
        out += ["## Not included (couldn't be read)", ""] + [f"- {u}" for u in unreadable] + [""]
    return "\n".join(out)
