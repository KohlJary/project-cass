"""
The one capped loop: model -> tools -> model, for any turn kind.

- Written against a small ModelClient interface. Only the Anthropic
  implementation exists so far (what autonomous sessions use today); Ollama
  and OpenAI implementations come with model routing (#64) and chat cutover.
- Capped by the spec's max_iterations (model calls per turn).
- Offers exactly the spec's tools. A call to anything else gets an error
  result saying it isn't available here, and nothing runs [C3].
- Guarded writes: before a tool that writes her memory runs, its text fields
  go through the voice guard (memory/voice_guard.py). A refusal or identity
  break is not stored; the model is told why.
- Before every model call it checks whether a conversation has arrived; if
  so the turn ends cleanly with status "interrupted" and the reason.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

from .spec import TurnSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model client
# ---------------------------------------------------------------------------

@dataclass
class ModelReply:
    text: str
    tool_calls: List[Dict[str, Any]]
    stop_reason: Optional[str]
    input_tokens: int
    output_tokens: int
    content: Any  # provider-native assistant content, echoed back next call


class ModelClient(Protocol):
    async def create(self, *, model: str, system: str, tools: List[Dict[str, Any]],
                     messages: List[Dict[str, Any]], max_tokens: int) -> ModelReply: ...


class AnthropicModelClient:
    def __init__(self, client: Any = None):
        if client is None:
            import anthropic
            client = anthropic.AsyncAnthropic()
        self._client = client

    async def create(self, *, model, system, tools, messages, max_tokens) -> ModelReply:
        kwargs: Dict[str, Any] = dict(model=model, max_tokens=max_tokens,
                                      system=system, messages=messages)
        if tools:
            kwargs["tools"] = tools
        response = await self._client.messages.create(**kwargs)
        text, calls = "", []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                calls.append({"id": block.id, "name": block.name, "input": block.input})
        usage = response.usage
        return ModelReply(
            text=text, tool_calls=calls, stop_reason=response.stop_reason,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            content=response.content,
        )


def resolve_model(spec: TurnSpec, current: str) -> str:
    """The model for a turn. Today: whatever the entry point already uses
    (sessions: DEFAULT_SESSION_MODEL via the runner), with retired IDs mapped.
    Model routing by spec.model_site is #64's to plug in here."""
    try:
        from llm_config import current_model_id
        return current_model_id(current)
    except Exception:  # llm_config unavailable: keep the model as given
        return current


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

WITHHELD_MESSAGE = ("Not kept: this reads as a refusal or as someone other than me, "
                    "not my own words, so it wasn't written to my memory (voice guard).")


@dataclass
class LoopStep:
    number: int
    text: str
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LoopOutcome:
    status: str = "completed"     # completed | max_turns | interrupted | error
    end_reason: Optional[str] = None
    error: Optional[str] = None
    steps: List[LoopStep] = field(default_factory=list)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    artifacts: List[Any] = field(default_factory=list)
    completion: Optional[Dict[str, Any]] = None   # session_complete input, if called
    withheld: List[Dict[str, Any]] = field(default_factory=list)


def guard_tool_input(spec: TurnSpec, name: str, tool_input: Dict[str, Any]) -> Optional[str]:
    """Return the refusal phrase if a memory-writing tool's text reads as one."""
    from memory.voice_guard import looks_like_refusal
    for field_name in spec.writes.guarded_fields.get(name, ()):
        value = tool_input.get(field_name) if isinstance(tool_input, dict) else None
        if isinstance(value, str):
            hit = looks_like_refusal(value)
            if hit:
                return hit
    return None


Executor = Callable[[str, Dict[str, Any]], Awaitable[Any]]
InterruptCheck = Callable[[], Optional[str]]


async def run_loop(
    *,
    spec: TurnSpec,
    client: ModelClient,
    model: str,
    system: str,
    tools: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    execute: Executor,
    interrupted: InterruptCheck = lambda: None,
    deadline: Optional[float] = None,
    max_tokens: int = 4096,
    end_tool: Optional[str] = "session_complete",
) -> LoopOutcome:
    out = LoopOutcome()
    offered = {t["name"] for t in tools}
    messages = list(messages)

    try:
        while True:
            reason = interrupted()
            if reason:
                out.status, out.end_reason = "interrupted", reason
                break
            if out.model_calls >= spec.max_iterations:
                out.status = "max_turns"
                out.end_reason = f"reached the cap of {spec.max_iterations} steps"
                break
            if deadline is not None and datetime.now().timestamp() > deadline:
                out.status, out.end_reason = "completed", "reached the time limit"
                break

            reply = await client.create(model=model, system=system, tools=tools,
                                        messages=messages, max_tokens=max_tokens)
            out.model_calls += 1
            out.input_tokens += reply.input_tokens
            out.output_tokens += reply.output_tokens
            step = LoopStep(out.model_calls, reply.text, reply.tool_calls,
                            input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)
            out.steps.append(step)
            messages.append({"role": "assistant", "content": reply.content})

            if not reply.tool_calls:
                out.status, out.end_reason = "completed", "I finished"
                break

            results = []
            ended = False
            for call in reply.tool_calls:
                name, tool_input = call["name"], call.get("input") or {}
                if name not in offered:
                    result: Any = {"error": f"{name} isn't available here "
                                            f"(not in this {spec.kind}'s tools)"}
                else:
                    refusal = guard_tool_input(spec, name, tool_input)
                    if refusal:
                        out.withheld.append({"tool": name, "matched": refusal})
                        result = {"error": WITHHELD_MESSAGE}
                    else:
                        try:
                            result = await execute(name, tool_input)
                        except Exception as e:  # a tool failure is a result, not a crash
                            logger.warning(f"[agent_loop] tool {name} failed: {e}")
                            result = {"error": str(e)}
                if isinstance(result, dict) and result.get("artifact"):
                    out.artifacts.append(result["artifact"])
                if name == end_tool and name in offered:
                    out.completion = dict(tool_input)
                    ended = True
                step.tool_results.append({"tool_name": name, "result": result})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": json.dumps(result, default=str) if isinstance(result, dict) else str(result),
                })
            messages.append({"role": "user", "content": results})
            if ended:
                out.status, out.end_reason = "completed", "I said I was done"
                break
    except Exception as e:
        logger.error(f"[agent_loop] {spec.kind} turn failed: {e}", exc_info=True)
        out.status, out.error = "error", str(e)
    return out
