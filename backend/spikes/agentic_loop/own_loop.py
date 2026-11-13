"""
Arm B: our own provider-neutral loop.

Claude Code's design, not its code: the turn ends when the model says it's
done (the done tool, or a reply with no tool calls), not at a small round cap;
a few general file tools plus her own; the agenda file is her working state.
History is kept in a neutral form, and each provider adapter translates it.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .common import TASK, RunRecord, system_prompt, tool_set

# Rough $ per million tokens (input, output), for the cost column only.
PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}

FILE_TOOLS: List[Dict[str, Any]] = [
    {"name": "read_file", "description": "Read a file in your workspace.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Create or overwrite a file in your workspace.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace one exact occurrence of old_text with new_text in a workspace file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"},
                                                        "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "list_files", "description": "List files in your workspace (optionally under a folder).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "search_files", "description": "Search your workspace files for a regular expression; returns matching lines.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]


# ---------------------------------------------------------------------------
# Workspace tools (fenced)
# ---------------------------------------------------------------------------

def _inside(ws: Path, rel: str) -> Optional[Path]:
    p = (ws / (rel or ".")).resolve()
    return p if p == ws or ws in p.parents else None


def run_file_tool(ws: Path, name: str, a: Dict[str, Any]) -> str:
    if name == "list_files":
        base = _inside(ws, a.get("path", "."))
        if not base or not base.exists():
            return "No such folder in your workspace."
        return "\n".join(str(p.relative_to(ws)) for p in sorted(base.rglob("*")) if p.is_file()) or "(empty)"
    if name == "search_files":
        try:
            rx = re.compile(a.get("pattern", ""), re.IGNORECASE)
        except re.error as e:
            return f"Bad pattern: {e}"
        hits = []
        for p in sorted(ws.rglob("*")):
            if p.is_file():
                for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{p.relative_to(ws)}:{n}: {line[:200]}")
        return "\n".join(hits[:80]) or "No matches."
    p = _inside(ws, a.get("path", ""))
    if not p:
        return "That path is outside your workspace."
    if name == "read_file":
        return p.read_text(errors="replace") if p.is_file() else "No such file."
    if name == "write_file":
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a.get("content", ""))
        return f"Wrote {p.relative_to(ws)}."
    if name == "edit_file":
        if not p.is_file():
            return "No such file."
        text = p.read_text()
        old = a.get("old_text", "")
        if not old or text.count(old) != 1:
            return f"old_text must occur exactly once (found {text.count(old) if old else 0})."
        p.write_text(text.replace(old, a.get("new_text", ""), 1))
        return f"Edited {p.relative_to(ws)}."
    return f"Unknown tool {name}."


# ---------------------------------------------------------------------------
# Provider adapters: neutral history -> provider request -> neutral reply
# ---------------------------------------------------------------------------
# Neutral history: {"role": "user", "text"} | {"role": "assistant", "text", "calls": [{id, name, input}]}
#                  | {"role": "tool", "results": [{id, name, content}]}

class AnthropicAdapter:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()

    def call(self, model, system, tools, history, max_tokens=4096) -> Tuple[str, List[Dict], int, int]:
        msgs = []
        for h in history:
            if h["role"] == "user":
                msgs.append({"role": "user", "content": h["text"]})
            elif h["role"] == "assistant":
                blocks = ([{"type": "text", "text": h["text"]}] if h["text"] else []) + [
                    {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]} for c in h["calls"]]
                msgs.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "(nothing)"}]})
            else:
                msgs.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]} for r in h["results"]]})
        r = self.client.messages.create(model=model, system=system, tools=tools, messages=msgs, max_tokens=max_tokens)
        text = "".join(b.text for b in r.content if b.type == "text")
        calls = [{"id": b.id, "name": b.name, "input": b.input} for b in r.content if b.type == "tool_use"]
        return text, calls, r.usage.input_tokens, r.usage.output_tokens


class OpenAIAdapter:
    """OpenAI's API, or anything that speaks it (Ollama's /v1)."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        from openai import OpenAI
        self.client = OpenAI(base_url=base_url, api_key=api_key or os.environ.get("OPENAI_API_KEY") or "none")

    def call(self, model, system, tools, history, max_tokens=4096) -> Tuple[str, List[Dict], int, int]:
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        for h in history:
            if h["role"] == "user":
                msgs.append({"role": "user", "content": h["text"]})
            elif h["role"] == "assistant":
                m: Dict[str, Any] = {"role": "assistant", "content": h["text"] or None}
                if h["calls"]:
                    m["tool_calls"] = [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"], "arguments": json.dumps(c["input"])}}
                                       for c in h["calls"]]
                msgs.append(m)
            else:
                for r in h["results"]:
                    msgs.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
        fns = [{"type": "function", "function": {"name": t["name"], "description": t["description"][:1000],
                                                 "parameters": t["input_schema"]}} for t in tools]
        r = self.client.chat.completions.create(model=model, messages=msgs, tools=fns, max_tokens=max_tokens)
        choice = r.choices[0].message
        calls = []
        for i, tc in enumerate(choice.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_unparsed": tc.function.arguments}
            calls.append({"id": tc.id or f"call_{i}", "name": tc.function.name, "input": args})
        u = r.usage
        return choice.content or "", calls, (u.prompt_tokens if u else 0), (u.completion_tokens if u else 0)


class OllamaAdapter:
    """Ollama's native /api/chat, so num_ctx can be set (its OpenAI endpoint ignores it).
    LiteLLM's ollama_chat route, used by the SDK arm, calls the same API."""

    def __init__(self, base_url: str = "http://localhost:11434", num_ctx: int = 32768):
        import httpx
        self.http = httpx.Client(base_url=base_url, timeout=900)
        self.num_ctx = num_ctx

    def call(self, model, system, tools, history, max_tokens=4096) -> Tuple[str, List[Dict], int, int]:
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        for h in history:
            if h["role"] == "user":
                msgs.append({"role": "user", "content": h["text"]})
            elif h["role"] == "assistant":
                m: Dict[str, Any] = {"role": "assistant", "content": h["text"] or ""}
                if h["calls"]:
                    m["tool_calls"] = [{"function": {"name": c["name"], "arguments": c["input"]}} for c in h["calls"]]
                msgs.append(m)
            else:
                for r in h["results"]:
                    msgs.append({"role": "tool", "content": r["content"], "tool_name": r["name"]})
        fns = [{"type": "function", "function": {"name": t["name"], "description": t["description"][:1000],
                                                 "parameters": t["input_schema"]}} for t in tools]
        r = self.http.post("/api/chat", json={"model": model, "messages": msgs, "tools": fns, "stream": False,
                                              "options": {"num_ctx": self.num_ctx, "num_predict": max_tokens}})
        r.raise_for_status()
        d = r.json()
        msg = d.get("message", {})
        calls = [{"id": f"call_{len(history)}_{i}", "name": tc["function"]["name"],
                  "input": tc["function"].get("arguments") or {}}
                 for i, tc in enumerate(msg.get("tool_calls") or [])]
        return msg.get("content") or "", calls, d.get("prompt_eval_count", 0), d.get("eval_count", 0)


def adapter_for(provider: str):
    if provider == "anthropic":
        return AnthropicAdapter()
    if provider == "openai":
        return OpenAIAdapter()
    if provider == "ollama":
        return OllamaAdapter()
    raise ValueError(provider)


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

NUDGE = ("(You haven't called done. If you're finished, update your agenda and call done. "
         "If you meant to do something, do it now with a tool call rather than describing it.)")


def run(ws: Path, provider: str, model: str, max_steps: int = 60, max_tokens_total: int = 1_500_000,
        nudges: int = 0) -> RunRecord:
    ws = ws.resolve()
    rec = RunRecord(arm=f"own_loop/{provider}" + (f"+nudge{nudges}" if nudges else ""), model=model)
    adapter = adapter_for(provider)
    system = system_prompt(ws)
    file_names = {t["name"] for t in FILE_TOOLS}
    tools = FILE_TOOLS + tool_set()
    history: List[Dict[str, Any]] = [{"role": "user", "text": TASK}]
    try:
        while True:
            if rec.steps >= max_steps:
                rec.ended_how = "cap"
                break
            if rec.input_tokens + rec.output_tokens > max_tokens_total:
                rec.ended_how = "budget"
                break
            text, calls, tin, tout = adapter.call(model, system, tools, history)
            rec.steps += 1
            rec.input_tokens += tin
            rec.output_tokens += tout
            history.append({"role": "assistant", "text": text, "calls": calls})
            rec.transcript.append({"step": rec.steps, "text": text, "calls": calls})
            if not calls:
                if nudges > 0:
                    nudges -= 1
                    rec.transcript.append({"step": rec.steps, "nudge": NUDGE})
                    history.append({"role": "user", "text": NUDGE})
                    continue
                rec.ended_how = "no_tool_calls"
                break
            results = []
            for c in calls:
                if c["name"] in file_names:
                    rec.tool_calls.append({"name": c["name"], "input": c["input"]})
                    out = run_file_tool(ws, c["name"], c["input"])
                else:
                    out = rec.spike_tool(c["name"], c["input"])
                results.append({"id": c["id"], "name": c["name"], "content": out})
            history.append({"role": "tool", "results": results})
            rec.transcript.append({"step": rec.steps, "results": [{"name": r["name"], "content": r["content"][:500]} for r in results]})
            if rec.done_summary is not None:
                rec.ended_how = "done"
                break
    except Exception as e:  # a spike reports failures, it doesn't hide them
        rec.ended_how, rec.error = "error", f"{type(e).__name__}: {e}"
    rec.ended = time.time()
    if model in PRICES:
        pi, po = PRICES[model]
        rec.cost_usd = round(rec.input_tokens / 1e6 * pi + rec.output_tokens / 1e6 * po, 4)
    elif provider == "ollama":
        rec.cost_usd = 0.0
    return rec
