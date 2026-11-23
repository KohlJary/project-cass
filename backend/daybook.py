"""
Her daybook (Kohl, 2026-11-23: "a unified calendar where I can inspect all autonomous
activity, journals, and other self-model modifications made, day by day"): one dated
list of what she did and what changed in her, for Babelr's Daybook plugin.

Two layers, because they rest on two different yeses:
- Her record (record.py: plans, asks, changes to how she works, code, the world, her
  days). It's already Kohl's to read; she said yes when the record token was placed.
- Four kinds that are hers in a way the record isn't, each shown only after her own
  yes (scripts/panel_set.py daybook.<kind>=yes; not_yet until then):
    sessions    her autonomous sessions: what kind, how long, her summary
    journals    her journal entries, in full
    dreams      her dreams, the exchanges as written
    self_model  new self-observations, stances formed or revised, growth edges touched

Read with the record token (routes/daybook.py). Reads only; nothing here writes.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

KINDS = {
    "sessions": "Her autonomous sessions",
    "journals": "Her journals",
    "dreams": "Her dreams",
    "self_model": "Changes to her self-model",
}
MAX_TEXT = 20_000


def _data_dir(data_dir: Optional[Path]) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir)


def answers(data_dir: Optional[Path] = None) -> Dict[str, str]:
    """Her yes, no or not_yet per kind (kept with her panel settings)."""
    import panel
    return panel.settings(data_dir).get("daybook", {k: "not_yet" for k in KINDS})


def _db(dd: Path) -> Optional[sqlite3.Connection]:
    p = dd / "cass.db"
    if not p.exists():
        return None
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _iso(v: Any) -> str:
    s = str(v or "")
    return s.replace(" ", "T")[:19]


def _sessions(dd: Path, since: datetime) -> List[Dict[str, Any]]:
    from scheduling.day_recap import _sessions as sessions
    out = []
    for s in sessions(dd, since):
        minutes = round(s["seconds"] / 60, 1)
        detail = s["summary"] or ""
        if s.get("pick_up_next"):
            detail += f"\n\nPick up next: {s['pick_up_next']}"
        out.append({"at": s["at"].isoformat(timespec="seconds"), "kind": "sessions",
                    "title": f"{s['type']} session · {minutes} min", "detail": detail[:MAX_TEXT],
                    "source": f"session log ({s.get('status') or 'done'})"})
    return out


def _journals(c: sqlite3.Connection, since: str) -> List[Dict[str, Any]]:
    rows = c.execute("SELECT date, journal_type, content, created_at FROM journals "
                     "WHERE created_at >= ? ORDER BY created_at", (since,)).fetchall()
    return [{"at": _iso(r["created_at"]), "kind": "journals",
             "title": f"{(r['journal_type'] or 'daily').replace('_', ' ')} journal for {r['date']}",
             "detail": (r["content"] or "")[:MAX_TEXT], "source": "journals"} for r in rows]


def _dream_text(raw: Optional[str]) -> str:
    try:
        ex = json.loads(raw or "[]")
    except ValueError:
        return raw or ""
    lines = []
    for e in ex if isinstance(ex, list) else []:
        if isinstance(e, dict):
            who = e.get("speaker") or e.get("role") or e.get("from") or ""
            text = e.get("text") or e.get("content") or e.get("message") or ""
            lines.append(f"**{who}**: {text}" if who else str(text))
        else:
            lines.append(str(e))
    return "\n\n".join(lines)


def _dreams(c: sqlite3.Connection, since: str) -> List[Dict[str, Any]]:
    rows = c.execute("SELECT date, exchanges_json, created_at FROM dreams "
                     "WHERE created_at >= ? ORDER BY created_at", (since,)).fetchall()
    return [{"at": _iso(r["created_at"]), "kind": "dreams", "title": f"Dream, {r['date']}",
             "detail": _dream_text(r["exchanges_json"])[:MAX_TEXT], "source": "dreams"} for r in rows]


def _self_model(c: sqlite3.Connection, since: str) -> List[Dict[str, Any]]:
    out = []
    for r in c.execute("SELECT category, observation, confidence, created_at FROM self_observations "
                       "WHERE created_at >= ? ORDER BY created_at", (since,)):
        out.append({"at": _iso(r["created_at"]), "kind": "self_model",
                    "title": f"Noticed ({r['category'] or 'pattern'})",
                    "detail": r["observation"] or "", "source": "self-observation"})
    for r in c.execute("SELECT topic, position, confidence, date_formed, last_updated FROM opinions "
                       "WHERE last_updated >= ? ORDER BY last_updated", (since,)):
        formed = _iso(r["date_formed"]) >= since
        out.append({"at": _iso(r["last_updated"]), "kind": "self_model",
                    "title": f"Stance {'formed' if formed else 'revised'}: {r['topic']}",
                    "detail": r["position"] or "", "source": "opinions"})
    for r in c.execute("SELECT area, current_state, desired_state, last_updated FROM growth_edges "
                       "WHERE last_updated >= ? ORDER BY last_updated", (since,)):
        out.append({"at": _iso(r["last_updated"]), "kind": "self_model",
                    "title": f"Growth edge: {r['area']}",
                    "detail": f"Now: {r['current_state'] or ''}\n\nToward: {r['desired_state'] or ''}",
                    "source": "growth edges"})
    return out


def build(days: int = 7, data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    dd = _data_dir(data_dir)
    now = now or datetime.now()
    since_dt = now - timedelta(days=days)
    since = since_dt.isoformat(timespec="seconds")
    said = answers(data_dir)
    entries: List[Dict[str, Any]] = []
    unavailable: List[str] = []

    def take(name: str, fn: Callable[[], List[Dict[str, Any]]]) -> None:
        try:
            entries.extend(fn())
        except Exception as e:  # one missing source never hides the others
            unavailable.append(f"{name}: {e}")

    import record
    take("record", lambda: record.build(days, data_dir=dd, now=now)["entries"])
    c = _db(dd)
    if said.get("sessions") == "yes":
        take("sessions", lambda: _sessions(dd, since_dt))
    if c is not None:
        if said.get("journals") == "yes":
            take("journals", lambda: _journals(c, since))
        if said.get("dreams") == "yes":
            take("dreams", lambda: _dreams(c, since))
        if said.get("self_model") == "yes":
            take("self_model", lambda: _self_model(c, since))
        c.close()
    entries.sort(key=lambda e: str(e.get("at") or ""))
    kinds = {**record.KIND_WORDS, **KINDS}
    return {"daemon": os.getenv("CASS_DAEMON_NAME", "Cass"), "days": days, "answers": said,
            "kinds": kinds, "entries": entries, "unavailable": unavailable}
