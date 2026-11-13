"""
Her tools in the loop: the core set she chose, and the rest found on demand.

Phase 2 of docs/design/agent-loop.md. In chat, a keyword in the message
decides which tool groups she is shown (agent_client.get_tools). In the loop
nothing is guessed:

  * her core set is always there: her always-on chat tools, plus tasks,
    calendar and babelr_read (her choice, 2026-11-13);
  * find_tools searches everything else tool_router can run, by what she
    wants to do; use_tool calls one of them;
  * tools that reach a person (send, post, DM) wait for phase 4's `say`;
  * every search and call goes in a usage log, and a tool she reaches for
    through use_tool often enough is promoted into the set she's offered
    directly (PROMOTE_*), so the core grows from how she works.

Tools she has switched off with modify_tool_access stay off here too.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

FIND_TOOL = "find_tools"
USE_TOOL = "use_tool"

FIND_TOOLS_DEFS: List[Dict[str, Any]] = [
    {"name": FIND_TOOL,
     "description": ("Search my other tools (research, wiki, goals, outreach, dreams, creative work, "
                     "home, Discord, and more) by what I want to do. Returns names, descriptions and "
                     "input schemas; call one with use_tool."),
     "input_schema": {"type": "object",
                      "properties": {"query": {"type": "string",
                                               "description": "What I want to do, in plain words"}},
                      "required": ["query"]}},
    {"name": USE_TOOL,
     "description": "Call one of my other tools by name (find it with find_tools first).",
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"},
                                     "input": {"type": "object",
                                               "description": "The tool's input, per its schema"}},
                      "required": ["name"]}},
]

# A tool called through use_tool on this many different days within the
# window is offered directly from then on, up to PROMOTE_MAX tools.
PROMOTE_DAYS = 3
PROMOTE_WINDOW_DAYS = 14
PROMOTE_MAX = 8

FIND_LIMIT = 6

# Tools that reach a person (send, post, DM, submit for sending). Held back
# from find_tools until phase 4, where speaking goes through her own
# reach_out design as `say`; the seam block's "Not yet: reach out" stays true.
NOT_YET_FINDABLE = frozenset({
    "send_email", "submit_outreach_draft", "send_direct_message",
    "discord_respond", "discord_react", "babelr_post", "babelr_dm",
})

# Executor types whose tools only work inside a project (chat with a project open).
_PROJECT_ONLY = {"document", "consolidated_document"}


# ---------------------------------------------------------------------------
# The catalog: every tool definition tool_router can run
# ---------------------------------------------------------------------------

def _plain(t: Dict[str, Any]) -> Dict[str, Any]:
    """A definition without chat-only keys (cache_control)."""
    return {"name": t["name"], "description": t.get("description", ""),
            "input_schema": t.get("input_schema") or {"type": "object", "properties": {}}}


def router_catalog() -> Dict[str, Dict[str, Any]]:
    """Name -> definition for every tool her chat can be shown and the router
    can run, where the subsystem behind it is on (Babelr, Discord, Home
    Assistant). Blacklisted tools (modify_tool_access) are left out."""
    import agent_client
    from handlers.tool_router import TOOL_REGISTRY

    groups: List[Iterable[Dict[str, Any]]] = [[agent_client.CONSOLIDATED_JOURNAL_TOOL]]
    for attr in sorted(dir(agent_client)):
        if not attr.endswith("_TOOLS") or attr in ("HOME_ASSISTANT_TOOLS", "HOME_AUTOMATION_TOOLS"):
            continue
        value = getattr(agent_client, attr)
        if isinstance(value, list):
            groups.append(value)
    try:
        if agent_client.home_assistant_available():
            groups += [agent_client.HOME_ASSISTANT_TOOLS, agent_client.HOME_AUTOMATION_TOOLS]
    except Exception as e:
        logger.debug(f"[agent_loop] home assistant check failed: {e}")
    try:
        from babelr_organ.config import babelr_enabled
        if babelr_enabled():
            from handlers.babelr import BABELR_TOOLS
            groups.append(BABELR_TOOLS)
    except Exception as e:
        logger.debug(f"[agent_loop] babelr tools unavailable: {e}")
    try:
        from discord_bot.config import DISCORD_ENABLED
        if DISCORD_ENABLED:
            from handlers.discord import DISCORD_TOOLS
            groups.append(DISCORD_TOOLS)
    except Exception as e:
        logger.debug(f"[agent_loop] discord tools unavailable: {e}")
    # The consolidated single tools (task, calendar, journal, ...) are chat's
    # compact form; their consolidated executor is named here so the core can
    # still offer `journal`, but find_tools lists the plain tools.
    catalog: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for t in group:
            if not (isinstance(t, dict) and "name" in t and "input_schema" in t):
                continue
            executor = TOOL_REGISTRY.get(t["name"])
            if not executor or executor in _PROJECT_ONLY:
                continue
            catalog.setdefault(t["name"], _plain(t))
    return _without_blacklisted(catalog)


def _without_blacklisted(catalog: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    try:
        from tool_selector import filter_blacklisted_tools
        kept = {t["name"] for t in filter_blacklisted_tools(list(catalog.values()))}
    except Exception as e:
        logger.debug(f"[agent_loop] blacklist check skipped: {e}")
        return catalog
    return {n: d for n, d in catalog.items() if n in kept}


def covered_by(name: str) -> List[str]:
    """Plain tools a consolidated tool already reaches (journal -> recall_journal, ...)."""
    from handlers.tool_router import CONSOLIDATED_ACTION_MAP, TOOL_REGISTRY
    return list(CONSOLIDATED_ACTION_MAP.get(TOOL_REGISTRY.get(name, ""), {}).values())


def findable(catalog: Dict[str, Dict[str, Any]], offered: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """What find_tools searches: the catalog minus what's offered directly
    (and minus what an offered consolidated tool already reaches), minus the
    consolidated tools themselves."""
    from handlers.tool_router import TOOL_REGISTRY
    skip = set(offered)
    for name in list(skip):
        skip.update(covered_by(name))
    return {n: d for n, d in catalog.items()
            if n not in skip and n not in NOT_YET_FINDABLE
            and not TOOL_REGISTRY.get(n, "").startswith("consolidated_")}


# ---------------------------------------------------------------------------
# find_tools
# ---------------------------------------------------------------------------

_STOP = {"the", "and", "for", "with", "that", "this", "what", "want", "something",
         "about", "into", "from", "some", "can", "how", "use", "tool", "tools", "my"}


def _words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP]


def search(query: str, candidates: Dict[str, Dict[str, Any]], limit: int = FIND_LIMIT) -> List[Dict[str, Any]]:
    """Rank candidates by the query's words: a hit in the name counts more
    than one in the description; a word's stem (first 5 letters) counts less."""
    words = _words(query)
    scored = []
    for name, d in candidates.items():
        name_l = name.lower()
        desc_l = d.get("description", "").lower()
        score = 0
        for w in words:
            if w in name_l:
                score += 3
            elif w in desc_l:
                score += 1
            elif len(w) > 5 and (w[:5] in name_l or w[:5] in desc_l):
                score += 0.5
        if score:
            scored.append((score, name))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [candidates[n] for _, n in scored[:limit]]


def find_result(query: str, candidates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    hits = search(query, candidates)
    if hits:
        return {"tools": hits, "how": "Call one with use_tool(name, input)."}
    return {"tools": [], "how": ("Nothing matched those words. Try others; "
                                 f"there are {len(candidates)} tools to search.")}


# ---------------------------------------------------------------------------
# Usage log and promotion
# ---------------------------------------------------------------------------

def default_log_path() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "agent_loop" / "tool_usage.jsonl"


class UsageLog:
    """One JSON line per find_tools search and per use_tool call."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_log_path()

    def record(self, event: str, session_id: str, **fields: Any) -> None:
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "event": event,
                 "session": session_id, **fields}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError as e:
            logger.warning(f"[agent_loop] couldn't write the tool usage log: {e}")

    def entries(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def promoted(self, now: Optional[datetime] = None, *, days: int = PROMOTE_DAYS,
                 window_days: int = PROMOTE_WINDOW_DAYS, limit: int = PROMOTE_MAX) -> List[str]:
        """Tools she called through use_tool (successfully) on `days` or more
        different days in the last `window_days`, most-used first."""
        now = now or datetime.now()
        since = now - timedelta(days=window_days)
        used_on: Dict[str, set] = defaultdict(set)
        calls: Dict[str, int] = defaultdict(int)
        for e in self.entries():
            if e.get("event") != "use" or not e.get("ok"):
                continue
            try:
                at = datetime.fromisoformat(e["at"])
            except (KeyError, ValueError):
                continue
            if at < since or at > now:
                continue
            used_on[e["tool"]].add(at.date())
            calls[e["tool"]] += 1
        ranked = sorted((n for n, d in used_on.items() if len(d) >= days),
                        key=lambda n: (-len(used_on[n]), -calls[n], n))
        return ranked[:limit]


# ---------------------------------------------------------------------------
# Running router tools from the loop
# ---------------------------------------------------------------------------

RouterRun = Callable[[str, Dict[str, Any]], Awaitable[Any]]


def live_router(daemon_id: Optional[str]) -> RouterRun:
    """Run a tool through tool_router with the vessel's own managers (the
    same context factory chat uses). Tools that act for a person (tasks,
    calendar, user-model) act for her primary partner, as reach_out does."""
    async def run(name: str, tool_input: Dict[str, Any]) -> Any:
        import websocket_handlers as ws
        make_ctx = ws._state.get("create_tool_context")
        executors = ws._state.get("tool_executors")
        batch = ws._state.get("execute_tool_batch")
        if not (make_ctx and executors and batch):
            return {"error": "my tool context isn't set up in this process"}
        user_id = user_name = None
        try:
            from reach_out import display_name, find_primary_partner
            user_id = find_primary_partner(daemon_id) if daemon_id else None
            user_name = display_name(user_id) if user_id else None
        except Exception as e:
            logger.debug(f"[agent_loop] no primary partner for tools: {e}")
        ctx = make_ctx(user_id=user_id, user_name=user_name, conversation_id=None, project_id=None)
        results = await batch([{"id": "loop", "tool": name, "input": tool_input}], ctx, executors)
        r = results[0] if results else {"result": "No result", "is_error": True}
        return {"error": r["result"]} if r.get("is_error") else r["result"]
    return run


def is_error(result: Any) -> bool:
    return isinstance(result, dict) and "error" in result and len(result) == 1


class ToolBox:
    """What one turn can call: session tools (the runner's handlers), router
    tools, and find_tools / use_tool over the rest. `execute` is the loop's
    executor."""

    def __init__(self, *, offered: Sequence[str], session_tools: Iterable[str],
                 run_session: Callable[[str, Dict[str, Any]], Awaitable[Any]],
                 run_router: RouterRun, catalog: Dict[str, Dict[str, Any]],
                 log: UsageLog, session_id: str, end_tool: Optional[str] = None):
        self.offered = list(offered)
        self.session_tools = set(session_tools)
        self.run_session = run_session
        self.run_router = run_router
        self.catalog = catalog
        self.findable = findable(catalog, self.offered)
        self.log = log
        self.session_id = session_id
        self.reserved = {FIND_TOOL, USE_TOOL} | ({end_tool} if end_tool else set())
        self.found: List[str] = []
        self.used: List[str] = []

    async def _run(self, name: str, tool_input: Dict[str, Any]) -> Any:
        if name in self.session_tools:
            return await self.run_session(name, tool_input)
        return await self.run_router(name, tool_input)

    async def execute(self, name: str, tool_input: Dict[str, Any]) -> Any:
        if name == FIND_TOOL:
            query = str(tool_input.get("query") or "")
            result = find_result(query, self.findable)
            names = [t["name"] for t in result["tools"]]
            self.found.extend(n for n in names if n not in self.found)
            self.log.record("find", self.session_id, query=query, results=names)
            return result
        if name == USE_TOOL:
            inner = str(tool_input.get("name") or "")
            inner_input = tool_input.get("input") or {}
            if not isinstance(inner_input, dict):
                return {"error": "use_tool's input must be an object"}
            if inner in self.reserved:
                return {"error": f"call {inner} directly, not through use_tool"}
            if inner not in self.findable and inner not in self.offered:
                return {"error": f"no tool named {inner!r}; find_tools searches by what I want to do"}
            result = await self._run(inner, inner_input)
            ok = not is_error(result)
            self.used.append(inner)
            self.log.record("use", self.session_id, tool=inner, ok=ok)
            return result
        return await self._run(name, tool_input)
