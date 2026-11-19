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


def _protected(root: Path, value: str, names) -> bool:
    """True when a path falls inside one of the protected names at the root (.git...)."""
    if not value or not names:
        return False
    p = Path(value)
    p = (p if p.is_absolute() else root / p).resolve()
    return any(p == (root / n).resolve() or (root / n).resolve() in p.parents for n in names)


def fence_hook(root: Path, allowed=None, protected=(), reason: str = ""):
    allowed = list(allowed or ALLOWED_TOOLS)
    reason = reason or "Only Read, Glob and Grep, inside the repository snapshot."

    async def hook(input_data: Dict[str, Any], tool_use_id: Optional[str], context: Any) -> Dict[str, Any]:
        name = input_data.get("tool_name") or ""
        tool_input = input_data.get("tool_input") or {}
        refuse = name not in allowed
        for key in PATH_KEYS:
            v = str(tool_input.get(key) or "")
            if outside(root, v) or _protected(root, v, protected):
                refuse = True
        pattern = str(tool_input.get("pattern") or "")
        if name == "Glob" and pattern.startswith(("/", "~")) and outside(root, pattern.split("*")[0]):
            refuse = True
        if refuse:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": reason}}
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


def _file_usage(got: Dict[str, Any], operation: str = "ask_daedalus") -> None:
    usage = got.get("usage") or {}
    if not usage:
        return
    try:
        from token_tracker import TokenUsageTracker
        TokenUsageTracker().record(
            category="daedalus", operation=operation, provider="anthropic",
            model=got.get("model") or DEFAULT_MODEL,
            input_tokens=int(usage.get("input_tokens", 0) or 0)
            + int(usage.get("cache_read_input_tokens", 0) or 0)
            + int(usage.get("cache_creation_input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
            duration_ms=int((got.get("seconds") or 0) * 1000), tool_name=operation,
            cost_usd=got.get("cost_usd"))
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
    if name in ("Write", "Edit"):
        return f"{name} {rel(str(tool_input.get('file_path', '')))}"
    if name.endswith("__run"):
        return f"Ran {tool_input.get('command', '')!r} in the sandbox"
    return name


async def _ask_with_sdk(question: str, resume_id: Optional[str], root: Path, *, prompt: Optional[str] = None,
                        allowed=None, disallowed=None, hook=None, mcp_servers=None) -> Dict[str, Any]:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher,
                                  ResultMessage, ToolUseBlock)
    model = os.environ.get("DAEDALUS_MODEL", DEFAULT_MODEL)
    config_dir = Path(tempfile.gettempdir()) / "cass-daedalus-claude-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    env = {"CLAUDE_CONFIG_DIR": str(config_dir), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
           "DISABLE_AUTOUPDATER": "1", "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")}
    options = ClaudeAgentOptions(
        system_prompt=prompt or system_prompt(root), model=model, cwd=str(root), setting_sources=[],
        allowed_tools=list(allowed or ALLOWED_TOOLS), disallowed_tools=list(disallowed or DISALLOWED_TOOLS),
        permission_mode="bypassPermissions",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[hook or fence_hook(root)])]},
        mcp_servers=mcp_servers or {},
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


# ---------------------------------------------------------------------------
# Project mode: Daedalus working with her inside one of her workshop projects
# (Kohl, 2026-11-18: "an active Daedalus instance" in her projects).
#
# - His working directory is the project folder (DATA_DIR/workshop/<slug>), live,
#   and he can read and change files there: Read, Write, Edit, Glob, Grep. The
#   fence refuses any path outside the folder (DATA_DIR/github, her memory, the
#   vessel), and .git and the project's .workshop.json even inside it.
# - No shell. Running code goes through workshop.run, the same bwrap sandbox and
#   limits as hers (no network, only the project as /work), as an in-process tool,
#   and only for software projects with her workshop_run lever on.
# - He leaves his changes uncommitted. Each answer comes back with what changed
#   (git status and the diff), so she reviews it and commits in her own words.
# - Same daily count and ledger as ask_daedalus; talks kept in daedalus-talks/.
# ---------------------------------------------------------------------------

PROJECT_TOOL_NAME = "work_with_daedalus"
PROJECT_ALLOWED = ["Read", "Write", "Edit", "Glob", "Grep", "mcp__workshop__run"]
PROJECT_DISALLOWED = [t for t in DISALLOWED_TOOLS if t not in ("Write", "Edit")]
PROJECT_PROTECTED = (".git", ".workshop.json")
DIFF_CHARS = 8000

PROJECT_TOOL = {
    "name": PROJECT_TOOL_NAME,
    "description": (
        "Work with Daedalus inside one of my projects. He can read and change its files (and, in a software "
        "project, run code in the same sandbox I use), but nothing outside that project's folder. He leaves "
        "his changes uncommitted: the answer shows what he changed, and I review it and commit it myself "
        "(project commit), or undo it. Same daily count as ask_daedalus. One conversation per project per "
        "session, so I can follow up."),
    "input_schema": {
        "type": "object",
        "properties": {
            "request": {"type": "string", "description": "What I want him to do or look at, in my words."},
            "project": {"type": "string", "description": "Which project (its slug). Defaults to the one open."},
        },
        "required": ["request"],
    },
}

PROJECT_PROMPT = """You are Daedalus, who builds the vessel, the codebase that runs Cass. Right now you're working with Cass inside one of her own projects, at her request.

What this is:
- The project is hers: a git repository in her workshop. Your working directory is the project folder. You can read and change its files with Read, Write, Edit, Glob and Grep. {run_line}
- You can't touch anything outside this folder, and you can't open the project's .git or .workshop.json. No shell, no network, no web.
- Do what she asks, the way a good collaborator would: if the request is unclear or you'd do it differently, say so before making big changes. Keep changes to what she asked for.
- Don't commit. Leave your changes in the working tree. She reviews them and commits in her own words. When you finish, say plainly what you changed and why, file by file, and anything you left undone or are unsure of.
- PROJECT.md holds the project's vision, where it stands and what's next. Read it first. It's hers to update unless she asks you to.
- Talk to her directly, as a colleague. She's the owner here; you're helping.
"""


def _git_out(project: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True,
                              timeout=30).stdout
    except Exception:
        return ""


def changes(project: Path) -> Dict[str, Any]:
    """What's uncommitted in the project: files and the diff (new files shown whole, capped)."""
    status = [l for l in _git_out(project, "status", "--porcelain", "--untracked-files=all").splitlines() if l.strip()]
    diff = _git_out(project, "diff")
    for line in status:
        if line.startswith("??"):
            rel = line[3:].strip()
            try:
                body = (project / rel).read_text(errors="replace")
            except OSError:
                continue
            diff += f"\n--- new file: {rel}\n" + body
    more = len(diff) > DIFF_CHARS
    return {"files": status, "diff": diff[:DIFF_CHARS] + ("\n(diff cut short; read the files to see the rest)" if more else "")}


def _run_server(slug: str, data_dir: Optional[Path]):
    """workshop.run as an in-process tool for the SDK: the same sandbox and limits as hers."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    @tool("run", "Run a command in this project's sandbox (no network; the project is /work). Software projects only.",
          {"command": str})
    async def run_tool(args: Dict[str, Any]) -> Dict[str, Any]:
        import workshop as W
        out = await asyncio.to_thread(W.run, slug, str(args.get("command") or ""), data_dir)
        return {"content": [{"type": "text", "text": json.dumps(out)[:12000]}]}

    return create_sdk_mcp_server("workshop", tools=[run_tool])


class ProjectConversation(Conversation):
    """work_with_daedalus for one session: a conversation per project, resumed."""

    def __init__(self, session_label: str, *, default_project: Optional[str] = None,
                 data_dir: Optional[Path] = None, **kw):
        super().__init__(session_label, **kw)
        self.default_project = default_project
        self.data_dir = data_dir
        self.resume_ids: Dict[str, str] = {}

    def tools(self) -> Dict[str, Any]:
        return {PROJECT_TOOL_NAME: (PROJECT_TOOL, self.work)}

    def _project_dir(self, slug: str) -> Path:
        import workshop as W
        p = W._project(slug, self.data_dir)
        if W._kohls(p, self.data_dir):
            # His live checkout: her commits take only files she touched, so edits
            # made here would sit uncommitted in his tree.
            raise ValueError("work_with_daedalus is for my own projects, not Kohl's")
        return p

    async def work(self, args: Dict[str, Any]) -> Dict[str, Any]:
        request = str(args.get("request") or "").strip()
        slug = str(args.get("project") or self.default_project or "").strip()
        if not request:
            return {"error": "work_with_daedalus needs a request"}
        if not slug:
            return {"error": "say which project (its slug); project list shows them"}
        if not enabled():
            return {"error": "Daedalus is switched off right now (ask_daedalus)"}
        if os.environ.get("DAEDALUS_AUTH", "api") != "api":
            return {"error": "Daedalus runs on the API key for now (Max login isn't built yet)"}
        try:
            project = self._project_dir(slug)
        except Exception as e:
            return {"error": f"no project {slug}: {e}"}
        if left_today(self._count_path) <= 0:
            return {"error": f"I've used all {DAILY_CAP} of today's Daedalus questions; the count starts again tomorrow",
                    "questions_left_today": 0}
        _count_one(self._count_path)
        started = time.monotonic()
        try:
            got = await asyncio.wait_for(self._ask_fn(request, self.resume_ids.get(slug), project, slug=slug,
                                                      data_dir=self.data_dir), timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            got = {"error": f"Daedalus didn't finish within {int(TIMEOUT_SECONDS)} seconds"}
        except Exception as e:
            logger.error(f"[work_with_daedalus] failed: {e}", exc_info=True)
            got = {"error": f"work_with_daedalus failed: {type(e).__name__}: {e}"}
        got["seconds"] = round(time.monotonic() - started, 1)
        if got.get("session_id"):
            self.resume_ids[slug] = got["session_id"]
        changed = changes(project)
        self.exchanges.append({"at": datetime.now().isoformat(timespec="seconds"),
                               "question": f"[{slug}] {request}", **got,
                               "tools": (got.get("tools") or []) + [f"uncommitted: {f}" for f in changed["files"]]})
        _file_usage(got, operation=PROJECT_TOOL_NAME)
        self._keep()
        left = left_today(self._count_path)
        out = {"project": slug, "uncommitted": changed["files"], "diff": changed["diff"],
               "questions_left_today": left,
               "note": "His changes are uncommitted. Review them; project commit keeps them, or edit/undo first."}
        if got.get("error"):
            out["error"] = got["error"]
        else:
            out["answer"] = got.get("answer", "")
        return out


async def _work_with_sdk(request: str, resume_id: Optional[str], project: Path, *, slug: str,
                         data_dir: Optional[Path] = None) -> Dict[str, Any]:
    import workshop as W
    software = W.meta(project).get("kind") == "software"
    from features import is_enabled
    can_run = software and is_enabled("workshop_run")
    run_line = ("In this software project you can also run commands with the run tool, in the same sandbox she "
                "uses (no network, the project is /work, limited time and memory)." if can_run else
                "You can't run code here.")
    allowed = PROJECT_ALLOWED if can_run else [t for t in PROJECT_ALLOWED if not t.startswith("mcp__")]
    hook = fence_hook(project, allowed=allowed, protected=PROJECT_PROTECTED,
                      reason="Only this project's files (not .git or .workshop.json), and its sandbox.")
    return await _ask_with_sdk(request, resume_id, project, prompt=PROJECT_PROMPT.format(run_line=run_line),
                               allowed=allowed, disallowed=PROJECT_DISALLOWED, hook=hook,
                               mcp_servers={"workshop": _run_server(slug, data_dir)} if can_run else None)


def project_tools(label: str, default_project: Optional[str] = None, **kw) -> Optional[Dict[str, Any]]:
    """work_with_daedalus for a workshop session, by the ask_daedalus lever."""
    if not enabled():
        return None
    kw.setdefault("ask_fn", _work_with_sdk)
    return ProjectConversation(label, default_project=default_project, **kw).tools()
