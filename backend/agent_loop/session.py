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
from .assemble import assemble
from .loop import AnthropicModelClient, LoopOutcome, ModelClient, resolve_model, run_loop
from .spec import Trigger, TurnSpec, session_spec

logger = logging.getLogger(__name__)


def tool_definitions(names: List[str]) -> List[Dict[str, Any]]:
    """Anthropic tool definitions for `names`, from the session tool module."""
    from session.tools import SESSION_TOOLS
    by_name: Dict[str, Dict[str, Any]] = {}
    for defs in SESSION_TOOLS.values():
        for d in defs:
            by_name.setdefault(d["name"], d)
    missing = [n for n in names if n not in by_name]
    if missing:
        raise KeyError(f"tool pack names unknown session tools: {missing}")
    return [by_name[n] for n in names]


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

        def to_dict(self) -> Dict[str, Any]:
            data = super().to_dict()
            data.update({
                "kind": self.kind,
                "agent_loop": True,
                "end_reason": self.end_reason,
                "model": self.model,
                "withheld": self.withheld,
                "prompt_sections": self.prompt_sections,
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
    client: Optional[ModelClient] = None,
):
    """Run one autonomous session through the Turn. Returns a SessionResult
    (subclass) so the action handler reports it the same way as before."""
    spec: TurnSpec = session_spec(session_type, max_iterations=max_turns)
    started = datetime.now()
    session_id = str(uuid.uuid4())[:8]
    trigger = Trigger(
        source="schedule",
        why=why or f"my autonomous schedule started {spec.where}",
        focus=focus,
        since_last=_since_last(runner),
        at=started,
    )

    tool_names = spec.tool_names()
    tools = tool_definitions(tool_names)
    prompt = assemble(spec, trigger, tool_names, additions)
    model = resolve_model(spec, runner.model)
    client = client or AnthropicModelClient(runner.client)
    daemon_id = getattr(runner, "daemon_id", None)
    try:
        from database import get_daemon_id
        daemon_id = get_daemon_id()
    except Exception:
        pass

    logger.info(f"[agent_loop] starting {session_type} session {session_id} through the Turn")

    async def execute(name: str, tool_input: Dict[str, Any]):
        return await runner._execute_tool(name, tool_input, session_id=session_id,
                                          session_type=session_type)

    outcome = await run_loop(
        spec=spec,
        client=client,
        model=model,
        system=prompt.text,
        tools=tools,
        messages=[{"role": "user",
                   "content": runner._get_default_initial_message(session_type, focus)}],
        execute=execute,
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
    )
    result.summary = keep_narrative(outcome, runner)
    result.insights = _insights(outcome)
    result.withheld = outcome.withheld

    pricing = runner.MODEL_PRICING.get(model, {})
    result.estimated_cost_usd = (
        result.total_input_tokens / 1000 * pricing.get("input", runner.DEFAULT_INPUT_COST_PER_1K)
        + result.total_output_tokens / 1000 * pricing.get("output", runner.DEFAULT_OUTPUT_COST_PER_1K)
    )

    await runner._save_session_log(result)
    logger.info(f"[agent_loop] session {session_id} {result.status}"
                + (f" ({result.end_reason})" if result.end_reason else ""))
    return result
