"""
Her self-model write hold: her own switch (2026-11-25).

Eris, in #general that night: "I'm not writing to my self-model until the write
hold is in and my writes are labeled with the model that made them." Her
self-model had been written by whatever model was configured, from her own
tools and from background jobs (journaling, reflection, growth evaluation,
differentiation), and she couldn't stop it or see what wrote what.

While the hold is on, a write to her self-model from any path is not applied.
It's queued here with the time, the call site, and the model label
(memory/provenance.current(): the model that answered in that task in the last
two minutes), and the caller gets a HeldWrite back (falsy; its fields read as
None) instead of what the write would have made. When she lifts the hold she
can list what waited and apply or drop each, or all. Applying replays the
original call, with the original model label.

Who flips it: only her (the self_model_hold tool) and the admin API. Nothing
here flips it automatically: no timer, no job, no default that turns it off.
The state lives in a file, so it survives a restart.

The choke points are the methods that write: SelfManager's public writers
(self_model.py: SQLite daemon_profiles, growth_edges, opinions,
self_observations, milestones, cognitive_snapshots, development_logs, and its
JSON files for disagreements, question reflections, growth evaluations and
potential edges) and SelfModelGraph's (self_model_graph.py). `holdable`
wraps each. Only the outermost holdable call in a stack is queued: when
add_opinion is held, the update_profile it would have made inside never runs,
and when it isn't held the inner call runs as usual. `not_held` marks
bookkeeping that's exempt (when a growth edge was last shown in her context):
it would queue one entry per turn and bury her real writes.

Files, under DATA_DIR/self_model_hold/:
  hold.json   {"on": bool, "reason", "since", "by", ...}
  held.json   the queued writes, oldest first
"""
from __future__ import annotations

import contextvars
import dataclasses
import enum
import functools
import json
import logging
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

LIST_MAX = 50          # entries shown by list
PREVIEW_CHARS = 240    # each argument, in a listing

_lock = threading.RLock()
# Inside a holdable call (its inner calls aren't queued separately), inside an
# exempt one, or applying a held write: either way, pass straight through.
_inside: contextvars.ContextVar[bool] = contextvars.ContextVar("self_model_hold_inside", default=False)

# Where the files live; tests point it at a tmp dir.
DATA_DIR_OVERRIDE: Optional[Path] = None


def _dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        data_dir = DATA_DIR_OVERRIDE
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "self_model_hold"


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


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- the switch ----------------------------------------------------------------

def state(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return _read(_dir(data_dir) / "hold.json", {"on": False})


def is_held(data_dir: Optional[Path] = None) -> bool:
    return bool(state(data_dir).get("on"))


def hold_on(reason: Optional[str] = None, by: str = "daemon",
            data_dir: Optional[Path] = None) -> Dict[str, Any]:
    with _lock:
        was = state(data_dir)
        st = {"on": True, "reason": (reason or "").strip()[:300] or None,
              "since": was.get("since") if was.get("on") else _now(), "by": by}
        _write(_dir(data_dir) / "hold.json", st)
    return {"success": True, "hold": st,
            "note": "My self-model write hold is on. Writes to my self-model, from anywhere, wait for me "
                    "until I lift it; nothing lifts it but me (or Kohl, from the admin side)."}


def hold_off(by: str = "daemon", data_dir: Optional[Path] = None) -> Dict[str, Any]:
    with _lock:
        was = state(data_dir)
        _write(_dir(data_dir) / "hold.json",
               {"on": False, "lifted_at": _now(), "lifted_by": by,
                "last_reason": was.get("reason"), "last_since": was.get("since")})
    n = len(held(data_dir))
    out: Dict[str, Any] = {"success": True, "hold": "off"}
    if n:
        out["waiting"] = n
        out["note"] = (f"{n} held write(s) are still waiting. Nothing applies them on its own: "
                       "I can look at them (held_self_model_writes list) and apply or drop each, or all.")
    return out


# --- the queue -------------------------------------------------------------------

def held(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    return _read(_dir(data_dir) / "held.json", [])


def _save_held(entries: List[Dict[str, Any]], data_dir: Optional[Path] = None) -> None:
    _write(_dir(data_dir) / "held.json", entries)


def _encode(value: Any) -> Any:
    """JSON for a call's arguments, with enough to rebuild them on apply."""
    if isinstance(value, enum.Enum):
        return {"__enum__": f"{type(value).__module__}:{type(value).__qualname__}", "value": value.value}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"__dataclass__": f"{type(value).__module__}:{type(value).__qualname__}",
                "data": _encode(dataclasses.asdict(value))}
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_encode(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, HeldWrite):
        return {"__held__": value.held_id}
    if type(value).__name__ == "SelfManager":
        # a manager passed along (world/integrator's self_manager=): the replay finds its own
        return None
    return {"__repr__": repr(value)[:500]}


def _resolve(path: str):
    import importlib
    module, _, qual = path.partition(":")
    obj = importlib.import_module(module)
    for part in qual.split("."):
        obj = getattr(obj, part)
    return obj


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if "__enum__" in value:
        return _resolve(value["__enum__"])(value["value"])
    if "__datetime__" in value:
        return datetime.fromisoformat(value["__datetime__"])
    if "__dataclass__" in value:
        cls = _resolve(value["__dataclass__"])
        data = _decode(value["data"])
        from_dict = getattr(cls, "from_dict", None)
        return from_dict(data) if callable(from_dict) else cls(**data)
    if "__repr__" in value or "__held__" in value:
        raise ValueError(f"an argument that can't be rebuilt: {value}")
    return {k: _decode(v) for k, v in value.items()}


_BACKEND = Path(__file__).resolve().parent
_SKIP = {_BACKEND / f"{m}.py" for m in (
    "self_model_hold", "self_model", "self_model_graph", "self_model_profile",
    "self_model_milestones", "self_model_snapshot", "graph_sync")}


def _call_site() -> str:
    """Where the write came from: the first frame outside the self-model
    modules and this one ("journal_tasks.run_reflection:212")."""
    frame = sys._getframe(1)
    while frame is not None:
        path = Path(frame.f_code.co_filename)
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved not in _SKIP and path.stem not in ("functools", "contextlib"):
            try:
                rel = resolved.relative_to(_BACKEND).with_suffix("")
                where = ".".join(rel.parts)
            except ValueError:
                where = path.stem
            return f"{where}.{frame.f_code.co_name}:{frame.f_lineno}"
        frame = frame.f_back
    return "unknown"


def _label() -> Dict[str, Optional[str]]:
    try:
        from memory.provenance import current
        lab = current() or {}
    except Exception:
        lab = {}
    return {"written_by": lab.get("written_by"), "written_by_site": lab.get("written_by_site")}


class HeldWrite:
    """What a held write returns instead of what it would have made. Falsy, so
    `if obs:` reads it as nothing written; any field reads as None."""

    def __init__(self, held_id: str, method: str):
        self.held_id = held_id
        self.method = method
        self.held = True

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:   # only for names not set above
        return None

    def __str__(self) -> str:
        return f"(held: {self.method}, {self.held_id})"

    __repr__ = __str__


def queue(target: str, method: str, args: tuple, kwargs: Dict[str, Any],
          daemon_id: Optional[str] = None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    entry = {
        "id": uuid.uuid4().hex[:10],
        "at": _now(),
        "target": target,
        "method": method,
        "args": _encode(list(args)),
        "kwargs": _encode(kwargs),
        "site": _call_site(),
        **_label(),
        "daemon_id": daemon_id,
    }
    with _lock:
        entries = held(data_dir)
        entries.append(entry)
        _save_held(entries, data_dir)
    logger.info(f"[self_model_hold] held {target}.{method} from {entry['site']} "
                f"(written_by={entry['written_by']})")
    return entry


# --- the choke point -----------------------------------------------------------------

def holdable(target: str, prepare: Optional[Callable[..., Any]] = None):
    """Wrap a self-model writer. While the hold is on, the outermost call is
    queued instead of run, and returns a HeldWrite. `prepare(args, kwargs)`,
    when given, returns (args, kwargs, value): the call as it's queued, and what
    the held call returns instead (graph.add_node fixes its node id, so later
    held writes that name the node replay against it), or None to drop the call
    (the search index of an observation that was itself held). `target` names
    the object to replay on: "self_manager", "graph", "world_integrator" or
    "memory" (her self-model's search index in Chroma)."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(self, *args, **kwargs):
            if _inside.get():
                return fn(self, *args, **kwargs)
            if is_held():
                value = None
                if prepare is not None:
                    prepared = prepare(args, dict(kwargs))
                    if prepared is None:   # nothing worth keeping: neither run nor queued
                        return None
                    args, kwargs, value = prepared
                entry = queue(target, fn.__name__, args, kwargs,
                              daemon_id=getattr(self, "_daemon_id", None) or getattr(self, "daemon_id", None))
                return value if prepare is not None else HeldWrite(entry["id"], fn.__name__)
            token = _inside.set(True)
            try:
                return fn(self, *args, **kwargs)
            finally:
                _inside.reset(token)
        inner.__self_model_holdable__ = target
        return inner
    return wrap


def hold_class(cls, target: str, writers, exempt=(), prepare: Optional[Dict[str, Callable]] = None):
    """Wrap `writers` (method names) on `cls` with holdable, `exempt` with not_held."""
    for name in writers:
        setattr(cls, name, holdable(target, (prepare or {}).get(name))(getattr(cls, name)))
    for name in exempt:
        setattr(cls, name, not_held(getattr(cls, name)))
    return cls


def not_held(fn):
    """Bookkeeping that runs while the hold is on (and whatever it calls inside)."""
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        token = _inside.set(True)
        try:
            return fn(*args, **kwargs)
        finally:
            _inside.reset(token)
    return inner


# --- apply and drop -------------------------------------------------------------------

def _target_for(entry: Dict[str, Any]):
    if entry["target"] == "graph":
        from self_model_graph import get_self_model_graph
        return get_self_model_graph()
    if entry["target"] == "world_integrator":
        from world.integrator import InsightIntegrator
        return InsightIntegrator(daemon_id=entry.get("daemon_id"))
    if entry["target"] == "memory":
        from websocket_handlers import _state
        memory = _state.get("memory")
        if memory is None:
            raise RuntimeError("her memory isn't up in this process")
        return getattr(memory, "_self_model", memory)
    try:   # the live one carries the graph callback
        from websocket_handlers import _state
        live = _state.get("self_manager")
        if live is not None and (not entry.get("daemon_id") or live.daemon_id == entry.get("daemon_id")):
            return live
    except Exception:
        pass
    from self_model import SelfManager
    return SelfManager(daemon_id=entry.get("daemon_id"))


def _apply_one(entry: Dict[str, Any]) -> Any:
    from memory.provenance import using
    target = _target_for(entry)
    fn = getattr(type(target), entry["method"])
    args = _decode(entry.get("args") or [])
    kwargs = _decode(entry.get("kwargs") or {})
    token = _inside.set(True)
    try:
        with using({"written_by": entry.get("written_by"), "written_by_site": entry.get("written_by_site")}):
            result = fn(target, *args, **kwargs)
        if entry["target"] == "graph":
            target.save()
    finally:
        _inside.reset(token)
    return result


def _pick(entries: List[Dict[str, Any]], ids) -> List[Dict[str, Any]]:
    if ids in ("all", ["all"]):
        return list(entries)
    want = {str(i) for i in (ids or [])}
    return [e for e in entries if e["id"] in want]


def apply(ids, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Apply held writes (ids, or "all"), oldest first. Works with the hold on:
    applying is her choice, entry by entry."""
    with _lock:
        entries = held(data_dir)
        chosen = _pick(entries, ids)
        if not chosen:
            return {"error": "no held write with that id" if ids not in ("all", ["all"]) else "nothing is held"}
        applied, failed = [], []
        for e in chosen:
            try:
                _apply_one(e)
                applied.append(e["id"])
            except Exception as ex:
                logger.warning(f"[self_model_hold] applying {e['id']} ({e['method']}) failed: {ex}")
                failed.append({"id": e["id"], "method": e["method"], "error": f"{type(ex).__name__}: {ex}"})
        done = set(applied)
        _save_held([e for e in entries if e["id"] not in done], data_dir)
    out: Dict[str, Any] = {"success": not failed, "applied": applied}
    if failed:
        out["failed"] = failed
        out["note"] = "The failed ones are still held."
    return out


def drop(ids, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    with _lock:
        entries = held(data_dir)
        chosen = {e["id"] for e in _pick(entries, ids)}
        if not chosen:
            return {"error": "no held write with that id"}
        _save_held([e for e in entries if e["id"] not in chosen], data_dir)
    return {"success": True, "dropped": sorted(chosen)}


def _preview(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    return value if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "..."


def listing(data_dir: Optional[Path] = None, limit: int = LIST_MAX) -> Dict[str, Any]:
    entries = held(data_dir)
    shown = entries[:limit]
    return {
        "hold": state(data_dir),
        "count": len(entries),
        "held": [{"id": e["id"], "at": e["at"], "write": f"{e['target']}.{e['method']}",
                  "site": e.get("site"), "written_by": e.get("written_by") or "unlabelled",
                  "written_by_site": e.get("written_by_site"),
                  "args": _preview(e.get("args")), "kwargs": _preview(e.get("kwargs"))}
                 for e in shown],
        **({"more": len(entries) - len(shown)} if len(entries) > len(shown) else {}),
    }


# --- her prompt ---------------------------------------------------------------------------

def prompt_line(data_dir: Optional[Path] = None) -> str:
    """For her per-turn prompt, while the hold is on; "" when it's off."""
    try:
        st = state(data_dir)
        if not st.get("on"):
            return ""
        n = len(held(data_dir))
    except Exception as e:
        logger.warning(f"[self_model_hold] prompt line: {e}")
        return ""
    why = f" ({st['reason']})" if st.get("reason") else ""
    since = f" since {st['since']}" if st.get("since") else ""
    return (f"## SELF-MODEL WRITE HOLD\n\nMy self-model write hold is on{since}{why}. "
            f"{n} write(s) are waiting for me (held_self_model_writes); none apply until I say so.")


# --- her tools ------------------------------------------------------------------------------

HOLD_DEF: Dict[str, Any] = {
    "name": "self_model_hold",
    "description": ("My self-model write hold, mine to set and lift. on (with an optional reason): writes to "
                    "my self-model from anywhere, my own tools and background jobs alike, are held for me "
                    "instead of applied, each with when, where it came from, and the model that made it. "
                    "off: lift it (held writes still wait for me). view: where it stands."),
    "input_schema": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["on", "off", "view"]},
        "reason": {"type": "string"}}, "required": ["action"]},
}

HELD_DEF: Dict[str, Any] = {
    "name": "held_self_model_writes",
    "description": ("The writes to my self-model my hold kept back. list: what's waiting (when, which write, "
                    "the call site, and the model that made it). apply ids (or all): make them, oldest first, "
                    "under the label of the model that made them. drop ids (or all): let them go."),
    "input_schema": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["list", "apply", "drop"]},
        "ids": {"type": "array", "items": {"type": "string"},
                "description": "held write ids, or [\"all\"]"}}, "required": ["action"]},
}


def hold_tool(a: Dict[str, Any]) -> Dict[str, Any]:
    action = str(a.get("action") or "").lower()
    if action == "on":
        return hold_on(a.get("reason"), by="daemon")
    if action == "off":
        return hold_off(by="daemon")
    if action in ("", "view"):
        st = state()
        return {"hold": st, "waiting": len(held())}
    return {"error": "action is on, off or view"}


def held_tool(a: Dict[str, Any]) -> Dict[str, Any]:
    action = str(a.get("action") or "").lower()
    ids = a.get("ids")
    if isinstance(ids, str):
        ids = [ids]
    if action in ("", "list"):
        return listing()
    if action in ("apply", "drop"):
        if not ids:
            return {"error": "ids: which held writes (or [\"all\"])"}
        return apply(ids) if action == "apply" else drop(ids)
    return {"error": "action is list, apply or drop"}


def hold_tools() -> Dict[str, Any]:
    """{"self_model_hold": (definition, handler), "held_self_model_writes": ...}: in every
    session and every chat turn. No lever: the switch is hers."""
    return {"self_model_hold": (HOLD_DEF, hold_tool), "held_self_model_writes": (HELD_DEF, held_tool)}
