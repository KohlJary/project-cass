"""
Autonomous sessions as Turns (lever `agent_loop`, off by default).

The first entry point moved onto the loop: the one with least at stake
(docs/design/agent-loop.md, Migration step 1). It reuses the existing
GenericSessionRunner for what isn't changing: its tool handlers and managers,
its Anthropic client and model, its default opening message, and its session
log format and folder (so the admin views keep listing these sessions).

What's different from the legacy runner.run_session:
  - the system prompt comes from assemble(): kernel, seam block, self-context,
    felt state, then the activity's instructions;
  - tools come from the session's packs (a superset of the activity's old set);
  - memory-writing tool input goes through the voice guard;
  - calling session_complete ends the session (the old loop kept going);
  - a conversation arriving ends it cleanly, with the reason recorded;
  - the narrative it keeps is voice-guarded too.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from memory.voice_guard import looks_like_refusal

from . import interrupt
from . import tools as tools_mod
from .assemble import assemble
from .loop import LoopOutcome, ModelClient, model_client_for, resolve_model, run_loop
from .spec import Trigger, TurnSpec, session_spec

logger = logging.getLogger(__name__)


def _session_tool_defs() -> Dict[str, Dict[str, Any]]:
    from session.tools import SESSION_TOOLS
    by_name: Dict[str, Dict[str, Any]] = {}
    for defs in SESSION_TOOLS.values():
        for d in defs:
            by_name.setdefault(d["name"], d)
    return by_name


def tool_definitions(names: List[str], catalog: Optional[Dict[str, Dict[str, Any]]] = None,
                     *, strict: bool = True, extra: Optional[List[Dict[str, Any]]] = None
                     ) -> List[Dict[str, Any]]:
    """Definitions for `names`: session tools first (session/tools.py), then
    her router tools (`catalog`, agent_loop.tools.router_catalog), then
    find_tools / use_tool. With strict=False, names with no definition (a
    subsystem that's off, a tool she switched off) are dropped, not raised."""
    from .workspace import WORKSPACE_TOOLS
    by_name = dict(_session_tool_defs())
    for d in tools_mod.FIND_TOOLS_DEFS + WORKSPACE_TOOLS:
        by_name.setdefault(d["name"], d)
    if catalog:
        for n, d in catalog.items():
            by_name.setdefault(n, d)
    for d in extra or []:
        by_name.setdefault(d["name"], d)
    missing = [n for n in names if n not in by_name]
    if missing and strict:
        raise KeyError(f"tool pack names unknown tools: {missing}")
    return [by_name[n] for n in names if n in by_name]


def _since_last(runner) -> Optional[str]:
    try:
        logs = runner.list_session_logs(limit=1)
    except Exception as e:
        logger.debug(f"[agent_loop] no session history: {e}")
        return None
    if not logs or not logs[0].get("started_at"):
        return None
    try:
        then = datetime.fromisoformat(logs[0]["started_at"])
    except ValueError:
        return None
    minutes = int((datetime.now() - then).total_seconds() // 60)
    if minutes < 90:
        gap = f"{max(minutes, 1)} minutes"
    elif minutes < 48 * 60:
        gap = f"{minutes // 60} hours"
    else:
        gap = f"{minutes // (24 * 60)} days"
    kind = (logs[0].get("session_type") or "session").replace("_", " ")
    return f"{gap} (a {kind} session)"


def _session_result_cls():
    from session.generic_runner import SessionResult

    @dataclass
    class TurnSessionResult(SessionResult):
        """SessionResult plus what the Turn adds, in the same log file."""
        kind: str = "session"
        end_reason: Optional[str] = None
        model: Optional[str] = None
        withheld: List[Dict[str, Any]] = field(default_factory=list)
        prompt_sections: List[str] = field(default_factory=list)
        provider: Optional[str] = None
        cache_read_tokens: int = 0
        cache_write_tokens: int = 0
        nudges: int = 0
        promoted_tools: List[str] = field(default_factory=list)
        tools_found: List[str] = field(default_factory=list)
        tools_used_via_find: List[str] = field(default_factory=list)
        workspace_changed: List[str] = field(default_factory=list)

        def to_dict(self) -> Dict[str, Any]:
            data = super().to_dict()
            data.update({
                "kind": self.kind,
                "agent_loop": True,
                "end_reason": self.end_reason,
                "model": self.model,
                "withheld": self.withheld,
                "prompt_sections": self.prompt_sections,
                "provider": self.provider,
                "cache_read_tokens": self.cache_read_tokens,
                "cache_write_tokens": self.cache_write_tokens,
                "nudges": self.nudges,
                "promoted_tools": self.promoted_tools,
                "tools_found": self.tools_found,
                "tools_used_via_find": self.tools_used_via_find,
                "workspace_changed": self.workspace_changed,
            })
            return data

    return TurnSessionResult


def keep_narrative(outcome: LoopOutcome, runner) -> Optional[str]:
    """The narrative this session keeps: what she said when she ended it, or
    her last words; with the reason if it ended early. Voice-guarded."""
    text = None
    if outcome.completion and outcome.completion.get("summary"):
        text = str(outcome.completion["summary"])
    else:
        last = next((s.text for s in reversed(outcome.steps) if s.text), None)
        if last:
            text = runner._extract_summary(last)
    if text:
        hit = looks_like_refusal(text)
        if hit:
            outcome.withheld.append({"tool": "narrative", "matched": hit})
            text = None
    if outcome.status == "interrupted":
        prefix = f"Ended early: {outcome.end_reason}."
        text = f"{prefix} {text}" if text else prefix
    return text


def _insights(outcome: LoopOutcome) -> List[str]:
    raw = (outcome.completion or {}).get("key_insights") or []
    kept = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str) and not looks_like_refusal(item):
            kept.append(item)
    return kept


async def run_session_turn(
    runner,
    *,
    session_type: str,
    additions: Optional[str] = None,
    duration_minutes: int = 30,
    focus: Optional[str] = None,
    max_turns: int = 10,
    why: Optional[str] = None,
    trigger_source: str = "schedule",
    client: Optional[ModelClient] = None,
    run_router: Optional[tools_mod.RouterRun] = None,
    catalog: Optional[Dict[str, Dict[str, Any]]] = None,
    usage_log: Optional[tools_mod.UsageLog] = None,
    workspace=None,
    wakes=None,
    can_wake: Optional[bool] = None,
):
    """Run one autonomous session through the Turn. Returns a SessionResult
    (subclass) so the action handler reports it the same way as before.
    `run_router`, `catalog`, `usage_log` and `workspace` default to the live ones."""
    import features
    from .spec import ACTIVITY_PACKS
    from .wakes import WakeBook, heartbeat_running, wake_tool
    from .workspace import WORKSPACE_TOOL_NAMES, Workspace
    started = datetime.now()
    session_id = str(uuid.uuid4())[:8]
    daemon_id = getattr(runner, "daemon_id", None)
    try:
        from database import get_daemon_id
        daemon_id = get_daemon_id()
    except Exception:
        pass

    if catalog is None:
        catalog = tools_mod.router_catalog()
    usage_log = usage_log or tools_mod.UsageLog()
    workspace = workspace or Workspace()
    wakes = wakes or WakeBook()
    say_def = tools_mod.say_tool(catalog) if features.is_enabled("reach_out") else None
    wake_def = wake_tool(ACTIVITY_PACKS)
    if can_wake is None:
        can_wake = heartbeat_running()
    session_names = set(_session_tool_defs())
    promoted = tuple(n for n in usage_log.promoted() if n in catalog)
    spec: TurnSpec = session_spec(session_type, max_iterations=max_turns,
                                  chapter_house="babelr_read" in catalog, promoted=promoted,
                                  can_say=say_def is not None, can_wake=can_wake)
    trigger = Trigger(
        source=trigger_source,
        why=why or f"my autonomous schedule started {spec.where}",
        focus=focus,
        since_last=_since_last(runner),
        at=started,
    )

    # Router tools not in the catalog are off (a subsystem that's down, or a
    # tool she switched off with modify_tool_access); they're left out.
    tool_names = [n for n in spec.tool_names()
                  if n in session_names or n in catalog
                  or n in ("find_tools", "use_tool", "say", "wake_me") + WORKSPACE_TOOL_NAMES]
    tools = tool_definitions(tool_names, catalog,
                             extra=[d for d in (say_def, wake_def) if d is not None])
    prompt = assemble(spec, trigger, tool_names, additions, workspace=workspace)
    model = resolve_model(spec, runner.model)
    if client is None:
        # The call site's assignment picks the provider: Claude by default,
        # or a GPT / local model if Settings > LLM assigns one.
        client, model = model_client_for("session.generic", model, runner.client)

    logger.info(f"[agent_loop] starting {session_type} session {session_id} through the Turn")

    async def run_session_tool(name: str, tool_input: Dict[str, Any]):
        return await runner._execute_tool(name, tool_input, session_id=session_id,
                                          session_type=session_type)

    box = tools_mod.ToolBox(
        offered=tool_names, session_tools=session_names, run_session=run_session_tool,
        run_router=run_router or tools_mod.live_router(daemon_id), catalog=catalog,
        log=usage_log, session_id=session_id, end_tool="session_complete",
        local={**{n: (lambda a, n=n: workspace.run(n, a, session_id)) for n in WORKSPACE_TOOL_NAMES},
               "wake_me": lambda a: wakes.request(a, session_id, ACTIVITY_PACKS)})

    outcome = await run_loop(
        spec=spec,
        client=client,
        model=model,
        system=prompt.text,
        tools=tools,
        messages=[{"role": "user",
                   "content": runner._get_default_initial_message(session_type, focus)}],
        execute=box.execute,
        interrupted=lambda: interrupt.conversation_since(started, daemon_id),
        deadline=started.timestamp() + duration_minutes * 60,
    )

    from session.generic_runner import SessionTurn
    Result = _session_result_cls()
    completed = datetime.now()
    result = Result(
        session_id=session_id,
        session_type=session_type,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        duration_seconds=(completed - started).total_seconds(),
        focus=focus,
        max_turns=max_turns,
        turns=[SessionTurn(turn_number=s.number, timestamp=s.at, role="assistant",
                           content=s.text, tool_calls=s.tool_calls, tool_results=s.tool_results,
                           token_usage={"input": s.input_tokens, "output": s.output_tokens})
               for s in outcome.steps],
        total_turns=outcome.model_calls,
        artifacts=outcome.artifacts,
        status=outcome.status,
        error=outcome.error,
        total_input_tokens=outcome.input_tokens,
        total_output_tokens=outcome.output_tokens,
        end_reason=outcome.end_reason,
        model=model,
        prompt_sections=[s.name for s in prompt.sections],
        provider=getattr(client, "provider", None),
        cache_read_tokens=outcome.cache_read_tokens,
        cache_write_tokens=outcome.cache_write_tokens,
        nudges=outcome.nudges,
        promoted_tools=list(promoted),
        tools_found=list(box.found),
        tools_used_via_find=list(box.used),
        workspace_changed=sorted({c["path"] for c in workspace.changes(limit=10_000)
                                  if c.get("session") == session_id}),
    )
    result.summary = keep_narrative(outcome, runner)
    result.insights = _insights(outcome)
    result.withheld = outcome.withheld

    if result.provider == "ollama":
        result.estimated_cost_usd = 0.0
    else:
        pricing = runner.MODEL_PRICING.get(model, {})
        per_in = pricing.get("input", runner.DEFAULT_INPUT_COST_PER_1K)
        # Anthropic bills cache reads at 0.1x input and cache writes at 1.25x.
        result.estimated_cost_usd = (
            (result.total_input_tokens + 0.1 * outcome.cache_read_tokens
             + 1.25 * outcome.cache_write_tokens) / 1000 * per_in
            + result.total_output_tokens / 1000 * pricing.get("output", runner.DEFAULT_OUTPUT_COST_PER_1K)
        )

    await runner._save_session_log(result)
    logger.info(f"[agent_loop] session {session_id} {result.status}"
                + (f" ({result.end_reason})" if result.end_reason else ""))
    return result
