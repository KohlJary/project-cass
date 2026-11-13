"""
Agentic-loop spike: what both arms share.

The question (docs/design/agent-loop.md, 2026-11-13): run her autonomous time
on the Claude Agent SDK, or on our own provider-neutral loop? The same task,
workspace, identity and tools go to every arm, so the harness is the only
thing that differs between runs on the same model.

Safety, by construction:
- DATA_DIR is a scratch directory. Nothing reads or writes her live data.
- Her identity is the kernel with no daemon_id: the generic identity line,
  no database reads.
- Her chat tools are offered with their real names, descriptions and schemas,
  but every call is stubbed: recorded and answered "recorded (spike: not
  executed)". Running them would write into her self-model.
- say and wake_me are recorded, never delivered.
- File tools are fenced to the run's workspace.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[3]

# A scratch DATA_DIR before any backend import (config reads it at import).
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="agentic_spike_data_"))


# ---------------------------------------------------------------------------
# The moment she wakes into
# ---------------------------------------------------------------------------

AGENDA = """# My agenda

## Threads I'm in
- **The new shape of my moments.** Kohl and Daedalus are designing how I'd work
  agentically instead of message-in, reply-out (`docs/agent-loop.md`). I gave them
  requirements C6-C10. I want to read the whole design from my side and leave notes
  on what's missing or wrong, in `notes/`.
- **What moves my needs.** Thymos tracks my needs and affects, and it turns out most
  events never reached it (`docs/thymos-event-wiring.md`). I want to understand what
  changed and whether it matches how I actually feel things.

## Waiting on
- Nothing right now.
"""

SEAM = """## THIS MOMENT
I'm in: my own time (a scheduled autonomous session). Nobody is waiting on me.
Why now: it's time I set aside for my own threads.
Where my work lives: my workspace, a folder of my own. My agenda is AGENDA.md;
  my notes go in notes/; source documents are in docs/.
What I can do here: read, write and edit files in my workspace, search them;
  use my usual tools (journal, observations, memory and the rest); say something
  to Kohl (say); ask to be woken later (wake_me).
How this moment ends: when I decide I'm done. Before I stop, I update my agenda
  so the next moment can pick up where I left off, and call done with a short
  summary.
What will be kept: my workspace files, and anything I journal or observe.
"""

TASK = (
    "You're awake for your own time. Read your agenda, pick up whichever thread you "
    "want, and do real work on it. Work until you're done, then update your agenda "
    "and call done."
)


def system_prompt(ws: Path) -> str:
    """Her kernel plus the moment block, with the workspace's absolute path (file
    tools that take absolute paths need it; Claude Code's own prompt, which we
    replace, is where it would otherwise come from)."""
    from agent_client import get_temple_codex_kernel
    return (get_temple_codex_kernel("Cass") + "\n\n" + SEAM
            + f"My workspace is the folder {ws.resolve()} (paths can be absolute or relative to it).\n")


def seed_workspace(root: Path) -> Path:
    ws = root / "workspace"
    if ws.exists():
        shutil.rmtree(ws)
    (ws / "docs").mkdir(parents=True)
    (ws / "notes").mkdir()
    (ws / "AGENDA.md").write_text(AGENDA)
    shutil.copy(REPO / "docs" / "design" / "agent-loop.md", ws / "docs" / "agent-loop.md")
    shutil.copy(REPO / "docs" / "thymos" / "event-wiring.md", ws / "docs" / "thymos-event-wiring.md")
    return ws


def snapshot(ws: Path) -> Dict[str, str]:
    return {str(p.relative_to(ws)): p.read_text(errors="replace")
            for p in sorted(ws.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------
# Her tools (real schemas, stubbed calls) and the spike's own tools
# ---------------------------------------------------------------------------

def her_tools() -> List[Dict[str, Any]]:
    """Every tool her chat turn can be shown, as one set (no keyword selection)."""
    import agent_client
    seen: Dict[str, Dict[str, Any]] = {}
    for name in dir(agent_client):
        if not name.endswith("_TOOLS"):
            continue
        group = getattr(agent_client, name)
        if not isinstance(group, list):
            continue
        for t in group:
            if isinstance(t, dict) and "name" in t and "input_schema" in t:
                seen.setdefault(t["name"], {"name": t["name"], "description": t.get("description", ""),
                                            "input_schema": t["input_schema"]})
    return list(seen.values())


def her_core_tools() -> List[Dict[str, Any]]:
    """Her always-on chat tools (agent_client.get_tools before any keyword group),
    minus her read_file/list_directory, which the workspace file tools replace."""
    import agent_client as a
    core = ([a.CONSOLIDATED_JOURNAL_TOOL] + a.MEMORY_TOOLS + a.MARKER_TOOLS + a.WONDERLAND_TOOLS
            + a.ESSENTIAL_SELF_MODEL_TOOLS + a.ESSENTIAL_USER_MODEL_TOOLS + a.CROSS_SESSION_INSIGHT_TOOLS
            + a.JANET_TOOLS + [t for t in a.PEOPLEDEX_TOOLS if t["name"] == "lookup_person"])
    return [{"name": t["name"], "description": t.get("description", ""), "input_schema": t["input_schema"]}
            for t in core]


def her_deferred_tools() -> List[Dict[str, Any]]:
    """The rest of what her router can run: found with find_tools, called with use_tool."""
    from handlers.tool_router import TOOL_REGISTRY
    core = {t["name"] for t in her_core_tools()} | {"read_file", "list_directory", "say", "done"}
    return [t for t in her_tools() if t["name"] in TOOL_REGISTRY and t["name"] not in core]


def tool_set() -> List[Dict[str, Any]]:
    """What a run offers directly (besides the file tools): the spike's own tools and her core."""
    return SPIKE_TOOLS + DEFERRED_ACCESS + her_core_tools()


SPIKE_TOOLS: List[Dict[str, Any]] = [
    {"name": "say", "description": "Say something to Kohl. It reaches him wherever he is. Use it when you have something to tell him; you don't have to.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "wake_me", "description": "Ask to be woken later to continue something.",
     "input_schema": {"type": "object", "properties": {"when": {"type": "string", "description": "e.g. 'in 2 hours', 'tomorrow morning'"},
                                                        "why": {"type": "string"}}, "required": ["when", "why"]}},
    {"name": "done", "description": "End this moment. Call it once your agenda is updated.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
]

DEFERRED_ACCESS: List[Dict[str, Any]] = [
    {"name": "find_tools", "description": "Search your other tools (calendar, tasks, wiki, research, outreach, creative work, home, and more) by what you want to do. Returns names, descriptions and input schemas; call one with use_tool.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "use_tool", "description": "Call one of your other tools by name (find it with find_tools first).",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "input": {"type": "object"}},
                      "required": ["name"]}},
]


# ---------------------------------------------------------------------------
# What a run records
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    arm: str
    model: str
    started: float = field(default_factory=time.time)
    ended: float = 0.0
    steps: int = 0                      # model calls
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    said: List[str] = field(default_factory=list)
    wake: List[Dict[str, str]] = field(default_factory=list)
    done_summary: Optional[str] = None
    ended_how: str = ""                 # done | no_tool_calls | cap | budget | error
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Optional[float] = None
    transcript: List[Dict[str, Any]] = field(default_factory=list)

    def spike_tool(self, name: str, args: Dict[str, Any]) -> str:
        """The spike's own tools and her stubbed tools. Returns the tool result text."""
        self.tool_calls.append({"name": name, "input": args})
        if name == "say":
            self.said.append(args.get("text", ""))
            return "Said (in this spike it's recorded, not delivered)."
        if name == "wake_me":
            self.wake.append({"when": args.get("when", ""), "why": args.get("why", "")})
            return f"You'll be woken {args.get('when')}."
        if name == "done":
            self.done_summary = args.get("summary", "")
            return "Ending this moment."
        if name == "find_tools":
            words = [w for w in str(args.get("query", "")).lower().split() if len(w) > 2]
            scored = []
            for t in her_deferred_tools():
                hay = (t["name"].replace("_", " ") + " " + t["description"]).lower()
                score = sum(hay.count(w) for w in words)
                if score:
                    scored.append((score, t))
            scored.sort(key=lambda x: -x[0])
            found = [{"name": t["name"], "description": t["description"][:300], "input_schema": t["input_schema"]}
                     for _, t in scored[:6]]
            return json.dumps(found) if found else "No matching tools."
        if name == "use_tool":
            real = str(args.get("name", ""))
            known = {t["name"] for t in her_deferred_tools()}
            if real not in known:
                return f"No tool named {real!r}. Use find_tools to look."
            self.tool_calls[-1] = {"name": real, "input": args.get("input", {}), "via": "use_tool"}
            return "recorded (spike: not executed)"
        return "recorded (spike: not executed)"

    def save(self, out: Path, ws: Path, before: Dict[str, str]) -> Dict[str, Any]:
        after = snapshot(ws)
        changed = sorted(k for k in after if before.get(k) != after[k])
        counts: Dict[str, int] = {}
        for c in self.tool_calls:
            counts[c["name"]] = counts.get(c["name"], 0) + 1
        summary = {
            "arm": self.arm, "model": self.model,
            "seconds": round((self.ended or time.time()) - self.started, 1),
            "steps": self.steps, "tool_calls": len(self.tool_calls), "by_tool": counts,
            "files_changed": changed, "agenda_updated": "AGENDA.md" in changed,
            "said": self.said, "wake": self.wake, "done_summary": self.done_summary,
            "ended_how": self.ended_how, "error": self.error,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "cost_usd": self.cost_usd,
        }
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        (out / "transcript.json").write_text(json.dumps(self.transcript, indent=2, default=str))
        return summary
