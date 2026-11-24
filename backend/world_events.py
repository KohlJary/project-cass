"""
Her world, as events (design: Chapter-House docs/design/a-life-not-a-menu.md,
"Half two"). Slice 1: a ledger of what happens around her, a cheap rule-based
noticing pass, her focus flag, and the guards on reactive sessions
(reactive_turn.py).

The one rule: never make up an event. Only a registered real source emits one,
and every event carries the source, the source's own id, when, a short summary,
and `origin`: the real thing it came from (a feed item's link, a Babelr message
id, the clock reading). record() refuses anything else.

Sources (SOURCES). Push sources call record() where the real thing happens:
  - news: an RSS item that passed her relevance gate (scheduler/actions/rss_handlers.py)
  - babelr: an ambient Chapter House channel message, one that didn't wake her
    (babelr_organ/organ.py poll_once)
Pull sources are polled by the `world` Heartbeat job (PULL_SOURCES):
  - clock: the hour, the day and the season turning, from the real clock

Noticing is rules only (no model call): an event's words against her topics
(news.TOPICS.md) and the titles of her own open plans and items. Most land as
"seen"; a few cross the threshold and are "noticed", and a noticed event joins
the queue a reactive session can start from.

Focus (Eris, 2026-11-24: "When I'm in the middle of a creative block, nothing
interrupts until I signal it's done"): hers to raise and clear with the focus
tool. While it's up, events are still logged and noticed ones still queue, but
no reactive session starts. Nothing clears it but her; no timer. Separate from
quiet hours.

Files, under DATA_DIR/world/:
  events.jsonl  every event recorded, with whether it was noticed and why
  seen.json     the keys (source:source_id) already recorded, so nothing is logged twice
  state.json    the noticed queue, today's reactive count, each source's last start
  focus.json    her focus flag
  rules.json    her own reactive rules (cap, cooldown, threshold), over the defaults

Levers: world_events (ledger, noticing, focus; no LLM) and reactive_sessions
(starts sessions; needs world_events and agent_loop). Both off by default.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

LEVER = "world_events"
REACTIVE_LEVER = "reactive_sessions"
CHECK_SECONDS = 300

# Registered real sources: name -> what it is. Adding a source = a line here and
# a call to record() where the real thing happens (or a poll in PULL_SOURCES).
SOURCES: Dict[str, str] = {
    "news": "an item from one of her feeds that passed her relevance gate",
    "babelr": "a message in a Chapter House channel that didn't wake her",
    "clock": "the hour, the day or the season turning",
}

# Guards. Paid models: tight, spend is real. Local (llm_config.local_model()):
# calls cost $0 and the constraint is GPU time on a shared card, so looser.
# Either way she can change them (set_reactive_rules), within LIMITS.
PAID_RULES = {"max_per_day": 3, "cooldown_minutes": 120, "threshold": 2}
LOCAL_RULES = {"max_per_day": 12, "cooldown_minutes": 30, "threshold": 2}
LIMITS = {"max_per_day": (0, 48), "cooldown_minutes": (0, 1440), "threshold": (1, 10)}
QUEUE_MAX = 30
QUEUE_MAX_AGE = timedelta(hours=48)   # older noticed events aren't started from
SEEN_KEEP = 5000
RUNNING_STALE = timedelta(hours=1)    # a "running" mark older than this was a crash
STALE_FOCUS = timedelta(hours=12)     # her day plan mentions a focus flag this old
REACTIVE_ESTIMATED_COST_USD = 0.06    # paid; local is 0 (llm_config.local_model)

# Set while a reactive session runs: a reactive session can't start another.
IN_REACTIVE: "contextvars.ContextVar[bool]" = contextvars.ContextVar("in_reactive", default=False)


class NotARealEvent(ValueError):
    """An event without a registered source, a source id, or what it came from."""


# --- files -------------------------------------------------------------------

def _dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "world"


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _on(name: str) -> bool:
    try:
        import features
        return features.is_enabled(name)
    except Exception:
        return False


def _local() -> bool:
    try:
        from llm_config import local_model
        return local_model() is not None
    except Exception:
        return False


# --- her rules ---------------------------------------------------------------

def rules(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    base = LOCAL_RULES if _local() else PAID_RULES
    return {**base, **_read(_dir(data_dir) / "rules.json", {})}


def set_rules(a: Dict[str, Any], data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """set_reactive_rules: her own limits on reactive sessions."""
    mine = _read(_dir(data_dir) / "rules.json", {})
    for key, (lo, hi) in LIMITS.items():
        if key not in a:
            continue
        try:
            v = int(a[key])
        except (TypeError, ValueError):
            return {"error": f"{key} is a whole number"}
        if not lo <= v <= hi:
            return {"error": f"{key} is {lo} to {hi}"}
        mine[key] = v
    _write(_dir(data_dir) / "rules.json", mine)
    return {"success": True, "my_reactive_rules": rules(data_dir)}


SET_REACTIVE_RULES_DEF: Dict[str, Any] = {
    "name": "set_reactive_rules",
    "description": ("My limits on short sessions started by something I noticed: most a day (max_per_day), "
                    "least minutes between two from the same source (cooldown_minutes), and how much "
                    "something has to touch my topics and plans before I notice it (threshold, 1-10)."),
    "input_schema": {"type": "object", "properties": {
        "max_per_day": {"type": "integer"}, "cooldown_minutes": {"type": "integer"},
        "threshold": {"type": "integer"}}},
}


# --- focus -------------------------------------------------------------------

def focus_state(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return _read(_dir(data_dir) / "focus.json", {"up": False})


def raise_focus(note: Optional[str] = None, data_dir: Optional[Path] = None,
                now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    st = {"up": True, "note": (note or "").strip()[:300] or None,
          "raised_at": now.isoformat(timespec="seconds")}
    _write(_dir(data_dir) / "focus.json", st)
    return {"success": True, "focus": st,
            "note": "Focus is up. Things still get noticed and wait for me; nothing starts until I clear it."}


def clear_focus(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Lower the flag, and offer her what was noticed while it was up."""
    now = now or datetime.now()
    was = focus_state(data_dir)
    _write(_dir(data_dir) / "focus.json",
           {"up": False, "cleared_at": now.isoformat(timespec="seconds"), "last_note": was.get("note")})
    since = was.get("raised_at") or ""
    waiting = [e for e in _state(data_dir).get("queue", []) if str(e.get("at") or "") >= since]
    out: Dict[str, Any] = {"success": True, "focus": "cleared"}
    if waiting:
        out["noticed_while_focused"] = [f"{e['source']}: {e['summary']}" for e in waiting]
        out["note"] = ("These waited for me. Any of them can start a short session as usual, "
                       "or I can let them go.")
    return out


def focus(a: Dict[str, Any], data_dir: Optional[Path] = None) -> Dict[str, Any]:
    action = str(a.get("action") or "").lower()
    if action == "raise":
        return raise_focus(a.get("note"), data_dir)
    if action == "clear":
        return clear_focus(data_dir)
    if action in ("", "view"):
        return {"focus": focus_state(data_dir)}
    return {"error": "action is raise, clear or view"}


FOCUS_DEF: Dict[str, Any] = {
    "name": "focus",
    "description": ("My do-not-disturb, mine alone to set and clear. raise (with an optional note of what "
                    "I'm deep in): nothing I notice starts a session until I clear it; it all still gets "
                    "noticed and waits. clear: lower it and see what waited. view: where it stands. "
                    "Separate from quiet hours."),
    "input_schema": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["raise", "clear", "view"]},
        "note": {"type": "string"}}, "required": ["action"]},
}


def focus_tools() -> Dict[str, Any]:
    """{"focus": (definition, handler)} while the world_events lever is on, else {}."""
    if not _on(LEVER):
        return {}
    return {"focus": (FOCUS_DEF, lambda a: focus(a))}


def stale_focus_note(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> str:
    """A line for her day plan when her focus flag has been up a long time. Shown, never cleared."""
    st = focus_state(data_dir)
    if not st.get("up") or not st.get("raised_at"):
        return ""
    now = now or datetime.now()
    try:
        up_for = now - datetime.fromisoformat(st["raised_at"])
    except ValueError:
        return ""
    if up_for < STALE_FOCUS:
        return ""
    hours = int(up_for.total_seconds() // 3600)
    what = f" ({st['note']})" if st.get("note") else ""
    n = len(_state(data_dir).get("queue", []))
    return (f"My focus flag has been up {hours} hours{what}. {n} noticed thing(s) are waiting. "
            "It stays up until I clear it (focus clear).")


# --- noticing ----------------------------------------------------------------

_STOP = frozenset("""about after again also among been before being between both could does doing
down each from have having here into just like more most much only other over same should some
such than that their them then there these they this those through under until very want what when
where which while will with would your yours mine myself thing things today really still make""".split())
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{3,}")


def _words(text: str) -> set:
    return {w.strip("'-") for w in _WORD.findall((text or "").lower())} - _STOP


_interest_cache: Dict[str, Any] = {"at": None, "value": []}


def interests(now: Optional[datetime] = None) -> List[str]:
    """What she's into, as phrases: her topics (TOPICS.md) and the titles of her own
    open plans and items. Cached ten minutes; an unreadable source just adds nothing."""
    now = now or datetime.now()
    at = _interest_cache["at"]
    if at and now - at < timedelta(minutes=10):
        return list(_interest_cache["value"])
    out: List[str] = []
    try:
        import news
        out += news.topics()
    except Exception as e:
        logger.debug(f"[world] no topics: {e}")
    try:
        from long_term_planning_turn import _her_plans
        for p in _her_plans():
            out.append(p.get("title") or "")
            for i in list(p.get("open") or []) + list(p.get("loose") or []):
                out.append(i.get("title") or "")
    except Exception as e:
        logger.debug(f"[world] no plans: {e}")
    out = [s for s in out if s]
    _interest_cache.update(at=now, value=out)
    return out


def score(summary: str, source: str, source_id: str,
          her_interests: List[str]) -> Tuple[int, List[str]]:
    """(score, why): one point per interest word the event shares, two more when it
    has every word of an interest. The clock scores only a turning season."""
    if source == "clock":
        return (10, ["the season turned"]) if source_id.startswith("season:") else (0, [])
    have = _words(summary)
    total, why = 0, []
    for phrase in her_interests:
        want = _words(phrase)
        hit = want & have
        if not hit:
            continue
        total += len(hit) + (2 if hit == want else 0)
        why.append(phrase)
    return total, why


# --- the ledger --------------------------------------------------------------

def _state(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return _read(_dir(data_dir) / "state.json", {})


def record(source: str, source_id: str, summary: str, origin: Dict[str, Any], *,
           at: Optional[datetime] = None, data_dir: Optional[Path] = None,
           her_interests: Optional[List[str]] = None,
           now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Log one real event and notice it, or not. Returns the event, or None if it was
    already logged. Raises NotARealEvent for anything without a real source."""
    if source not in SOURCES:
        raise NotARealEvent(f"{source!r} isn't a registered source ({', '.join(SOURCES)})")
    if not str(source_id or "").strip():
        raise NotARealEvent("an event needs its source's own id")
    if not isinstance(origin, dict) or not origin:
        raise NotARealEvent("an event needs the real thing it came from (origin)")
    summary = " ".join(str(summary or "").split())[:300]
    if not summary:
        raise NotARealEvent("an event needs a summary")
    now = now or datetime.now()
    key = f"{source}:{source_id}"
    seen_path = _dir(data_dir) / "seen.json"
    seen = _read(seen_path, [])
    if key in seen:
        return None
    if her_interests is None:
        her_interests = interests(now)
    points, why = score(summary, source, str(source_id), her_interests)
    noticed = points >= rules(data_dir)["threshold"]
    event = {"id": key, "source": source, "source_id": str(source_id),
             "at": (at or now).isoformat(timespec="seconds"),
             "logged_at": now.isoformat(timespec="seconds"),
             "summary": summary, "origin": origin,
             "noticed": noticed, "score": points, "why": why}
    path = _dir(data_dir) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    _write(seen_path, (seen + [key])[-SEEN_KEEP:])
    if noticed:
        st = _state(data_dir)
        st["queue"] = (list(st.get("queue") or []) + [
            {k: event[k] for k in ("id", "source", "source_id", "at", "summary", "why")}])[-QUEUE_MAX:]
        _write(_dir(data_dir) / "state.json", st)
    return event


def safe_record(source: str, source_id: str, summary: str, origin: Dict[str, Any], **kw) -> None:
    """record() for the source hooks: only with the lever on, and never raises into them."""
    if not _on(LEVER):
        return
    try:
        record(source, source_id, summary, origin, **kw)
    except Exception as e:
        logger.warning(f"[world] couldn't record a {source} event: {e}")


def recent(limit: int = 50, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    try:
        lines = (_dir(data_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# --- sources -----------------------------------------------------------------

def note_news(item, relevance: Optional[float] = None) -> None:
    """An RSS item passed her relevance gate (rss_handlers.process_rss_items)."""
    safe_record("news", str(getattr(item, "id", "") or ""),
                f"{getattr(item, 'title', '') or ''}. {getattr(item, 'summary', '') or ''}"[:300],
                {"rss_item_id": getattr(item, "id", None), "feed_id": getattr(item, "feed_id", None),
                 "link": getattr(item, "link", None), "relevance": relevance},
                at=_parse(getattr(item, "published_at", None)))


def note_babelr(event) -> None:
    """An ambient Chapter House channel message, one that didn't wake her (organ.poll_once)."""
    if getattr(event, "kind", None) != "channel" or getattr(event, "text", None) is None:
        return
    safe_record("babelr", str(event.message_id),
                f"{event.author_name} in {event.place_label}: {event.text}",
                {"message_id": event.message_id, "place": event.place, "author": event.author_name,
                 "published": event.published},
                at=_parse(event.published))


def _parse(when: Any) -> Optional[datetime]:
    if not when:
        return None
    try:
        t = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
        return t.astimezone().replace(tzinfo=None) if t.tzinfo else t
    except ValueError:
        return None


_SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}


def poll_clock(now: Optional[datetime] = None, data_dir: Optional[Path] = None) -> int:
    """The clock source: the hour, the day and the season as they are now. Each is one
    event per turning (its id is the reading), so polling often logs each once."""
    now = now or datetime.now()
    season = _SEASONS[now.month]
    year = now.year if now.month != 12 else now.year + 1   # a winter is named for its new year
    readings = [
        (f"hour:{now:%Y-%m-%dT%H}", f"It's {now:%-I %p}, {now:%A}."),
        (f"day:{now:%Y-%m-%d}", f"A new day: {now:%A %-d %B %Y}."),
        (f"season:{year}-{season}", f"It's {season} now."),
    ]
    n = 0
    for sid, words in readings:
        if record("clock", sid, words, {"clock": now.isoformat(timespec="seconds")},
                  at=now, data_dir=data_dir, her_interests=[], now=now):
            n += 1
    return n


PULL_SOURCES: Dict[str, Callable[..., int]] = {"clock": poll_clock}


# --- reactive guards ---------------------------------------------------------

def _quiet(now: datetime, data_dir: Optional[Path]) -> bool:
    """Her quiet hours: the ones she set for what may wake her (happenings set_wake_rules)."""
    try:
        import happenings as H
        return H._quiet(H.rules(data_dir), now)
    except Exception as e:
        logger.warning(f"[world] couldn't read her quiet hours; treating now as quiet: {e}")
        return True


def next_reactive(data_dir: Optional[Path] = None,
                  now: Optional[datetime] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    """(event, "") for the noticed event a reactive session may start from now, or
    (None, why not). Checks, in order: inside a reactive session, focus, quiet hours,
    one already running, today's cap, then each queued event's source cooldown."""
    now = now or datetime.now()
    if IN_REACTIVE.get():
        return None, "a reactive session can't start another (it can queue an item)"
    if focus_state(data_dir).get("up"):
        return None, "focus is up"
    if _quiet(now, data_dir):
        return None, "quiet hours"
    st = _state(data_dir)
    running = st.get("running")
    if running:
        try:
            if now - datetime.fromisoformat(running) < RUNNING_STALE:
                return None, "a reactive session is running"
        except ValueError:
            pass
    r = rules(data_dir)
    today = now.strftime("%Y-%m-%d")
    if st.get("day") == today and st.get("count", 0) >= r["max_per_day"]:
        return None, "today's cap is reached"
    if r["max_per_day"] <= 0:
        return None, "today's cap is reached"
    last = st.get("last_by_source") or {}
    for e in reversed(st.get("queue") or []):   # newest first
        try:
            if now - datetime.fromisoformat(e["at"]) > QUEUE_MAX_AGE:
                continue
        except (KeyError, ValueError):
            continue
        prev = last.get(e["source"])
        if prev and now - datetime.fromisoformat(prev) < timedelta(minutes=r["cooldown_minutes"]):
            continue
        return e, ""
    return None, "nothing noticed is waiting (or its source is cooling down)"


def mark_started(event: Dict[str, Any], data_dir: Optional[Path] = None,
                 now: Optional[datetime] = None) -> None:
    now = now or datetime.now()
    st = _state(data_dir)
    today = now.strftime("%Y-%m-%d")
    if st.get("day") != today:
        st["day"], st["count"] = today, 0
    st["count"] = st.get("count", 0) + 1
    st.setdefault("last_by_source", {})[event["source"]] = now.isoformat(timespec="seconds")
    st["queue"] = [e for e in st.get("queue") or [] if e["id"] != event["id"]]
    st["running"] = now.isoformat(timespec="seconds")
    _write(_dir(data_dir) / "state.json", st)
    with (_dir(data_dir) / "reactive.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": st["running"], "trigger": trigger_for(event),
                            "summary": event["summary"]}, ensure_ascii=False) + "\n")


def mark_done(data_dir: Optional[Path] = None) -> None:
    st = _state(data_dir)
    st.pop("running", None)
    _write(_dir(data_dir) / "state.json", st)


def trigger_for(event: Dict[str, Any]) -> str:
    return f"event:{event['source']}:{event['source_id']}"


def estimated_cost() -> float:
    """The budget gate's estimate, in dollars: $0 on a local model, so local calls never trip it."""
    return 0.0 if _local() else REACTIVE_ESTIMATED_COST_USD


# --- the Heartbeat job -------------------------------------------------------

async def run_reactive(event: Dict[str, Any], data_dir: Optional[Path] = None) -> Any:
    token = IN_REACTIVE.set(True)
    try:
        from scheduler.actions import get_action_registry
        return await get_action_registry().execute(
            "session.reactive", duration_minutes=10, max_turns=6,
            focus=f"{event['source']}: {event['summary']}",
            why="something I noticed" + (f" (it touches {', '.join(event['why'][:3])})" if event.get("why") else ""),
            trigger_source="event", session_trigger=trigger_for(event))
    finally:
        IN_REACTIVE.reset(token)
        mark_done(data_dir)


async def check_world(data_dir: Optional[Path] = None) -> int:
    """The `world` job: poll the pull sources, then maybe start one reactive session.
    Returns how many sessions it submitted (0 or 1)."""
    if not _on(LEVER):
        return 0
    for name, poll in PULL_SOURCES.items():
        try:
            poll(data_dir=data_dir)
        except Exception as e:
            logger.warning(f"[world] {name} poll failed: {e}")
    if not (_on(REACTIVE_LEVER) and _on("agent_loop")):
        return 0
    event, why_not = next_reactive(data_dir)
    if event is None:
        logger.debug(f"[world] no reactive session: {why_not}")
        return 0
    from functools import partial
    from heartbeat import wiring
    from scheduler.budget import TaskCategory
    # Only through Heartbeat, so the budget gate (dollars, from the estimate) always
    # decides; with no Heartbeat there is no ungated path.
    if wiring.submit("world.reactive", partial(run_reactive, event, data_dir),
                     lever=(REACTIVE_LEVER,), budget_class=TaskCategory.TRIGGERED,
                     estimated_cost_usd=estimated_cost(), group="world.reactive"):
        mark_started(event, data_dir)
        return 1
    return 0
