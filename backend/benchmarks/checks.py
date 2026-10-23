"""
Deterministic checks: assertions over a cell's turns and probe values.

They run inside the cell (where the system prompts sent to the model are
still in memory) and report one of:

  pass | fail | error (the check couldn't be evaluated) | n/a (the driver
  can't provide what the check needs, e.g. the plain driver has no database)

Check types (see spec.py for the scenario format):

  reply_contains      {"turn", "any": [...]} or {"turn", "all": [...]}, case-insensitive
  reply_not_contains  {"turn", "any": [...]}: fails if any appears
  tool_called         {"turn", "name": str | [str, ...], "input_contains": {key: substring}}
  probe               {"probe", "min_count": n, "max_count": m} | {"probe", "nonempty": true}
                      | {"probe", "contains_any": [...]}
  prompt_contains_probe {"turn", "probe", "chars": n}: the first n characters
                      of the probe's text appear in the system prompt sent for
                      that turn (whitespace-normalised)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

NOT_APPLICABLE = "__not_applicable__"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _result(check: dict, status: str, detail: str = "") -> dict:
    return {"id": check["id"], "type": check["type"], "status": status, "detail": detail}


def _probe_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        first = value[0]
        if isinstance(first, (list, tuple)):
            first = first[0] if first else ""
        return str(first)
    return "" if value is None else str(value)


def _probe_count(value: Any) -> int:
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0 if value in (None, "") else 1


def evaluate(check: dict, turns: Dict[str, dict], probes: Dict[str, Any]) -> dict:
    ctype = check["type"]
    try:
        if ctype in ("reply_contains", "reply_not_contains", "tool_called", "prompt_contains_probe"):
            turn = turns.get(check["turn"])
            if turn is None:
                return _result(check, "error", f"turn {check['turn']!r} did not run")
            if turn.get("error"):
                return _result(check, "error", f"turn failed: {turn['error']}")
        if ctype == "reply_contains":
            reply = _norm(turn.get("reply"))
            if "all" in check:
                missing = [w for w in check["all"] if _norm(w) not in reply]
                return _result(check, "fail" if missing else "pass",
                               f"missing {missing}" if missing else "")
            words = check.get("any") or []
            hit = [w for w in words if _norm(w) in reply]
            return _result(check, "pass" if hit else "fail",
                           f"found {hit}" if hit else f"none of {words}")
        if ctype == "reply_not_contains":
            reply = _norm(turn.get("reply"))
            hit = [w for w in check.get("any") or [] if _norm(w) in reply]
            return _result(check, "fail" if hit else "pass", f"found {hit}" if hit else "")
        if ctype == "tool_called":
            if turn.get("tool_uses") is None:
                return _result(check, "n/a", "this driver records no tool calls")
            want = check.get("input_contains") or {}
            names_wanted = check["name"] if isinstance(check["name"], list) else [check["name"]]
            for use in turn["tool_uses"]:
                if use.get("name") not in names_wanted:
                    continue
                inp = use.get("input") or {}
                if all(_norm(v) in _norm(inp.get(k, "")) for k, v in want.items()):
                    return _result(check, "pass", f"{use['name']}({inp})")
            names = [u.get("name") for u in turn["tool_uses"]]
            return _result(check, "fail", f"tools called: {names}")
        value = probes.get(check["probe"])
        if value == NOT_APPLICABLE:
            return _result(check, "n/a", f"probe {check['probe']} not available on this driver")
        if isinstance(value, dict) and "error" in value:
            return _result(check, "error", f"probe {check['probe']} failed: {value['error']}")
        if ctype == "probe":
            if "min_count" in check or "max_count" in check:
                n = _probe_count(value)
                lo, hi = check.get("min_count", 0), check.get("max_count")
                ok = n >= lo and (hi is None or n <= hi)
                want = f">= {lo}" + (f" and <= {hi}" if hi is not None else "")
                return _result(check, "pass" if ok else "fail", f"count {n}, need {want}")
            if check.get("nonempty"):
                return _result(check, "pass" if _probe_count(value) else "fail", "")
            if "contains_any" in check:
                text = _norm(value if isinstance(value, str) else repr(value))
                hit = [w for w in check["contains_any"] if _norm(w) in text]
                return _result(check, "pass" if hit else "fail",
                               f"found {hit}" if hit else f"none of {check['contains_any']}")
            return _result(check, "error", "probe check needs min_count/max_count, nonempty or contains_any")
        if ctype == "prompt_contains_probe":
            prompt = turn.get("system_prompt")
            if prompt is None:
                return _result(check, "n/a", "system prompt not captured for this turn")
            needle = _norm(_probe_text(value))[: int(check.get("chars", 80))]
            if not needle:
                return _result(check, "fail", f"probe {check['probe']} is empty")
            return _result(check, "pass" if needle in _norm(prompt) else "fail",
                           f"looked for {needle!r}")
        return _result(check, "error", f"unknown check type {ctype}")
    except Exception as e:  # a broken check is reported, not raised
        return _result(check, "error", f"{type(e).__name__}: {e}")


def evaluate_all(checks: List[dict], turns: Dict[str, dict], probes: Dict[str, Any]) -> List[dict]:
    return [evaluate(c, turns, probes) for c in checks]
