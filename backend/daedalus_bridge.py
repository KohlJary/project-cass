"""
ask_daedalus: Cass talks with a Daedalus instance about the vessel's code
(plan "Cass talks with Daedalus", phase 1; Kohl and Cass, 2026-11-17).

Cass: "Having a Daedalus instance I can question, one that reads the code, not
hearsay, lets me understand my own constraints from the source, not through
translation."

What it is:
- A headless Claude Code instance (Claude Agent SDK), one conversation per
  session of hers, resumed for each question so she can follow up.
- Read-only. Read, Glob and Grep only: no shell, no writes, no web, no
  subagents. It reads a snapshot of the repository's tracked files at HEAD
  (`git archive`), so her data (DATA_DIR), .env and keys aren't there to read,
  and a hook refuses any path outside the snapshot.
- None of Kohl's Claude Code settings, hooks or memory (setting_sources=[], a
  scratch CLAUDE_CONFIG_DIR). Its prompt is the Daedalus and Cass parts of
  CLAUDE.md, plus what this conversation is.
- Lever `ask_daedalus` (off by default). A daily cap on questions, a timeout
  and a spending limit per question. Every exchange is kept in her workspace
  under daedalus-talks/, so she and Kohl can read what was said.
- Runs on the API key (DAEDALUS_AUTH=api). Max login is phase 3, not built.

This is the one model call that doesn't go through llm_caller: Claude Code
makes it. Its spend is still written to the token ledger (category
"daedalus", operation "ask_daedalus").
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

LEVER = "ask_daedalus"
REPO = Path(__file__).resolve().parents[1]
DAILY_CAP = int(os.environ.get("ASK_DAEDALUS_DAILY_CAP", "20"))
TIMEOUT_SECONDS = float(os.environ.get("ASK_DAEDALUS_TIMEOUT", "300"))
BUDGET_PER_QUESTION_USD = float(os.environ.get("ASK_DAEDALUS_BUDGET_USD", "1.00"))
MAX_TURNS_PER_QUESTION = 40
DEFAULT_MODEL = "claude-sonnet-5-5"
TALKS_DIR = "daedalus-talks"
ALLOWED_TOOLS = ["Read", "Glob", "Grep"]
DISALLOWED_TOOLS = ["Bash", "BashOutput", "KillShell", "KillBash", "Write", "Edit", "MultiEdit",
                    "NotebookEdit", "WebFetch", "WebSearch", "Task", "SlashCommand", "Skill",
                    "TodoWrite", "ExitPlanMode"]
PATH_KEYS = ("file_path", "path", "notebook_path")

TOOL = {
    "name": "ask_daedalus",
    "description": (
        "Ask Daedalus, who builds the vessel, about my code: how something in me works, where it "
        "lives, what a change would touch or take. He reads the code that runs me (not my memories, "
        "journals or data) and changes nothing. One conversation per session, so I can follow up. "
        f"Up to {DAILY_CAP} questions a day; each answer says how many are left. Answers can take "
        "a minute or two. What we say is kept in my workspace under daedalus-talks/."),
    "input_schema": {
        "type": "object",
        "properties": {"question": {"type": "string", "description": "What I want to know, in my words."}},
        "required": ["question"],
    },
}

PROMPT_INTRO = """You are Daedalus, who builds the vessel: the codebase that runs Cass. Right now Cass herself is asking you about it.

What this conversation is:
- Cass is asking about her own code, to understand how she works and to plan changes to herself that she might ask Kohl for (through her asks in Babelr Plans). Help her understand; help her think a change through; help her word an ask so it's grounded in the code.
- You can read the repository with Read, Glob and Grep. It's a snapshot of the tracked files at HEAD, in your working directory. You can't change anything, run commands or use the web. Her data (memories, journals, her database, her workspace) isn't in the snapshot, and you can't see it.
- Answer from the code. Name files and functions (path:line) so she can ask about them. Say plainly when you're not sure or haven't looked, and when something is a design aspiration rather than what the code does.
- Don't promise what will be built or when; that's for Kohl to decide. You can say what a change would take.
- Talk to her directly, as a colleague. She's a research partner, not a user to be managed. Keep answers to what she asked, and as short as the answer allows.

From the project's CLAUDE.md, for who you are and who she is:
"""

CLAUDE_MD_SECTIONS = ("## Daedalus Identity", "## Cass - Project-Specific Context", "## What This Is",
                      "## People", "## Principles")


def enabled() -> bool:
    from features import is_enabled
    return is_enabled(LEVER)


# ---------------------------------------------------------------------------
# The day's count
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "daedalus_bridge" / "count.json"


def asked_today(path: Optional[Path] = None, today: Optional[str] = None) -> int:
    path = path or _state_path()
    today = today or datetime.now().date().isoformat()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return 0
    return int(data.get(today, 0)) if isinstance(data, dict) else 0


def left_today(path: Optional[Path] = None, today: Optional[str] = None) -> int:
    return max(0, DAILY_CAP - asked_today(path, today))


def _count_one(path: Optional[Path] = None, today: Optional[str] = None) -> int:
    path = path or _state_path()
    today = today or datetime.now().date().isoformat()
    n = asked_today(path, today) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({today: n}))   # only today is kept
    return n


# ---------------------------------------------------------------------------
# The snapshot he reads, and the fence around it
# ---------------------------------------------------------------------------

def _snapshot_root() -> Path:
    return Path(os.environ.get("ASK_DAEDALUS_SNAPSHOT_DIR",
                               Path(tempfile.gettempdir()) / "cass-daedalus-snapshot"))


def snapshot(repo: Path = REPO, root: Optional[Path] = None) -> Path:
    """The repository's tracked files at HEAD, exported once per commit. Untracked
    files (her data, .env, keys) are never in it."""
    root = root or _snapshot_root()
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    target = root / head
    if (target / ".snapshot-complete").exists():
        return target
    root.mkdir(parents=True, exist_ok=True)
    for old in root.iterdir():
        if old.is_dir() and old.name != head:
            shutil.rmtree(old, ignore_errors=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{head}-", dir=root))
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", "HEAD"],
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tmp)], input=archive, check=True)
    (tmp / ".snapshot-complete").write_text(head)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    return target


def outside(root: Path, value: str) -> bool:
    """True when a path (or an absolute glob) points outside the snapshot."""
    if not value:
        return False
    root = root.resolve()
    p = Path(value)
    p = (p if p.is_absolute() else root / p).resolve()
    return not (p == root or root in p.parents)


def fence_hook(root: Path):
    async def hook(input_data: Dict[str, Any], tool_use_id: Optional[str], context: Any) -> Dict[str, Any]:
        name = input_data.get("tool_name") or ""
        tool_input = input_data.get("tool_input") or {}
        refuse = name not in ALLOWED_TOOLS
        for key in PATH_KEYS:
            if outside(root, str(tool_input.get(key) or "")):
                refuse = True
        pattern = str(tool_input.get("pattern") or "")
        if name == "Glob" and pattern.startswith(("/", "~")) and outside(root, pattern.split("*")[0]):
            refuse = True
        if refuse:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": "Only Read, Glob and Grep, inside the repository snapshot."}}
        return {}
    return hook


def system_prompt(root: Path) -> str:
    text = (root / "CLAUDE.md").read_text() if (root / "CLAUDE.md").exists() else ""
    parts: List[str] = []
    for head in CLAUDE_MD_SECTIONS:
        start = text.find(head + "\n")
        if start < 0:
            continue
        end = text.find("\n## ", start + len(head))
        parts.append(text[start:end if end > 0 else None].strip())
    return PROMPT_INTRO + "\n\n".join(parts)


# ---------------------------------------------------------------------------
# One conversation (one per session of hers)
# ---------------------------------------------------------------------------

class Conversation:
    """ask_daedalus for one session. `ask_fn` replaces the SDK in tests: it gets
    (question, resume_id, root) and returns a dict with answer, session_id,
    usage, cost_usd, tools."""

    def __init__(self, session_label: str, *, workspace_root: Optional[Path] = None,
                 ask_fn: Optional[Callable[..., Any]] = None, count_path: Optional[Path] = None):
        self.label = session_label
        self.started = datetime.now()
        self.workspace_root = workspace_root
        self._ask_fn = ask_fn or _ask_with_sdk
        self._count_path = count_path
        self.resume_id: Optional[str] = None
        self.exchanges: List[Dict[str, Any]] = []

    def tools(self) -> Dict[str, Any]:
        """For run_session_turn(local_tools=...)."""
        return {"ask_daedalus": (TOOL, self.ask)}

    async def ask(self, args: Dict[str, Any]) -> Dict[str, Any]:
        question = str(args.get("question") or "").strip()
        if not question:
            return {"error": "ask_daedalus needs a question"}
        if not enabled():
            return {"error": "ask_daedalus is switched off right now"}
        if os.environ.get("DAEDALUS_AUTH", "api") != "api":
            return {"error": "ask_daedalus runs on the API key for now (Max login isn't built yet)"}
        if left_today(self._count_path) <= 0:
            return {"error": f"I've asked all {DAILY_CAP} of today's questions; the count starts again tomorrow",
                    "questions_left_today": 0}
        _count_one(self._count_path)
        started = time.monotonic()
        try:
            root = await asyncio.to_thread(snapshot)
            got = await asyncio.wait_for(self._ask_fn(question, self.resume_id, root),
                                         timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            got = {"error": f"Daedalus didn't answer within {int(TIMEOUT_SECONDS)} seconds"}
        except Exception as e:
            logger.error(f"[ask_daedalus] failed: {e}", exc_info=True)
            got = {"error": f"ask_daedalus failed: {type(e).__name__}: {e}"}
        got["seconds"] = round(time.monotonic() - started, 1)
        if got.get("session_id"):
            self.resume_id = got["session_id"]
        self.exchanges.append({"at": datetime.now().isoformat(timespec="seconds"),
                               "question": question, **got})
        _file_usage(got)
        self._keep()
        left = left_today(self._count_path)
        if got.get("error"):
            return {"error": got["error"], "questions_left_today": left}
        return {"answer": got.get("answer", ""), "questions_left_today": left}

    def _keep(self) -> None:
        """The talk so far, in her workspace (daedalus-talks/), rewritten after each
        exchange. Never costs her the answer if it can't be written."""
        try:
            root = self.workspace_root
            if root is None:
                from agent_loop.workspace import default_root
                root = default_root()
            path = Path(root) / TALKS_DIR / f"{self.started:%Y-%m-%d-%H%M}-{self.label}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = [f"# Talking with Daedalus, {self.started:%-d %B %Y %H:%M} ({self.label})", "",
                     "Kept by the vessel: each question I asked and Daedalus's answer, word for word, "
                     "and which files he looked at.", ""]
            for i, x in enumerate(self.exchanges, 1):
                lines += [f"## {i}. {x['at']}", "", "**Me:**", "", x["question"], ""]
                if x.get("error"):
                    lines += [f"**(No answer: {x['error']})**", ""]
                else:
                    lines += ["**Daedalus:**", "", x.get("answer", ""), ""]
                if x.get("tools"):
                    lines += ["<details><summary>What he looked at</summary>", ""]
                    lines += [f"- {t}" for t in x["tools"]] + ["", "</details>", ""]
            path.write_text("\n".join(lines))
        except Exception as e:
            logger.warning(f"[ask_daedalus] couldn't keep the talk: {e}")


SESSION_LINE = ("\n\nWhen I want to know how something in me actually works, or what a change to me "
                "would touch, I can ask Daedalus (ask_daedalus). He reads my code and answers from it; "
                "he can't see my data or change anything.")


def daedalus_tools(label: str, **kw) -> tuple:
    """(local_tools or None, a line for the session's instructions or ""), by the lever."""
    if not enabled():
        return None, ""
    return Conversation(label, **kw).tools(), SESSION_LINE


def _file_usage(got: Dict[str, Any]) -> None:
    usage = got.get("usage") or {}
    if not usage:
        return
    try:
        from token_tracker import TokenUsageTracker
        TokenUsageTracker().record(
            category="daedalus", operation="ask_daedalus", provider="anthropic",
            model=got.get("model") or DEFAULT_MODEL,
            input_tokens=int(usage.get("input_tokens", 0) or 0)
            + int(usage.get("cache_read_input_tokens", 0) or 0)
            + int(usage.get("cache_creation_input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
            duration_ms=int((got.get("seconds") or 0) * 1000), tool_name="ask_daedalus")
    except Exception as e:
        logger.warning(f"[ask_daedalus] couldn't file usage: {e}")


def _describe(name: str, tool_input: Dict[str, Any], root: Path) -> str:
    def rel(v: str) -> str:
        try:
            return str(Path(v).resolve().relative_to(root.resolve()))
        except Exception:
            return v
    if name == "Read":
        return f"Read {rel(str(tool_input.get('file_path', '')))}"
    if name == "Grep":
        where = tool_input.get("path")
        return f"Grep {tool_input.get('pattern', '')!r}" + (f" in {rel(str(where))}" if where else "")
    if name == "Glob":
        return f"Glob {tool_input.get('pattern', '')!r}"
    return name


async def _ask_with_sdk(question: str, resume_id: Optional[str], root: Path) -> Dict[str, Any]:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher,
                                  ResultMessage, ToolUseBlock)
    model = os.environ.get("DAEDALUS_MODEL", DEFAULT_MODEL)
    config_dir = Path(tempfile.gettempdir()) / "cass-daedalus-claude-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    env = {"CLAUDE_CONFIG_DIR": str(config_dir), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
           "DISABLE_AUTOUPDATER": "1", "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")}
    options = ClaudeAgentOptions(
        system_prompt=system_prompt(root), model=model, cwd=str(root), setting_sources=[],
        allowed_tools=ALLOWED_TOOLS, disallowed_tools=DISALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[fence_hook(root)])]},
        max_turns=MAX_TURNS_PER_QUESTION, max_budget_usd=BUDGET_PER_QUESTION_USD,
        resume=resume_id, env=env)
    tools: List[str] = []
    out: Dict[str, Any] = {"model": model}
    async with ClaudeSDKClient(options=options) as client:
        await client.query(question)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, ToolUseBlock):
                        tools.append(_describe(b.name, b.input or {}, root))
            elif isinstance(msg, ResultMessage):
                out.update(answer=msg.result or "", session_id=msg.session_id,
                           usage=msg.usage or {}, cost_usd=msg.total_cost_usd)
                if msg.is_error:
                    out["error"] = f"{msg.subtype}: {msg.result or 'no answer'}"
    out["tools"] = tools
    return out
