"""
Model clients for the loop: one neutral history, one adapter per provider.

The loop keeps its history in a provider-neutral form, and each client
translates it to its provider's request and the reply back. Ported from the
spike's own loop (backend/spikes/agentic_loop/own_loop.py); the decision to
keep our own loop rather than the Claude Agent SDK is in decisions.md
(2026-11-13) and docs/design/agent-loop.md.

Neutral history (what run_loop keeps):
    {"role": "user", "content": str}
    {"role": "assistant", "text": str, "calls": [{"id", "name", "input"}]}
    {"role": "tool", "results": [{"id", "name", "content": str}]}

Tool definitions are in Anthropic's shape ({name, description, input_schema});
the OpenAI and Ollama clients convert them.

Every request goes through llm_caller, so each lands in the token ledger under
its call site and admin overrides apply:
    Anthropic -> create_message (with prompt caching on the system prompt,
                 the tool list and the newest message)
    OpenAI    -> openai_raw (chat.completions with function tools)
    Ollama    -> ollama_raw (native /api/chat, so num_ctx can be set; Ollama's
                 OpenAI endpoint ignores it)

model_client_for() picks the client from the call site's assignment, so the
same turn runs on Claude, GPT or a local model by changing the assignment.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ModelReply:
    text: str
    tool_calls: List[Dict[str, Any]]
    stop_reason: Optional[str]
    input_tokens: int
    output_tokens: int
    content: Any = None  # provider-native reply, for logs and debugging only
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens


class ModelClient(Protocol):
    provider: str

    async def create(self, *, model: str, system: str, tools: List[Dict[str, Any]],
                     messages: List[Dict[str, Any]], max_tokens: int) -> ModelReply: ...


def _user_text(message: Dict[str, Any]) -> str:
    content = message.get("content", message.get("text", ""))
    if isinstance(content, str):
        return content
    # A block list (older callers): keep its text.
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def _function_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t.get("description", ""),
                          "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}}
            for t in tools]


def _parse_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    except (json.JSONDecodeError, TypeError):
        return {"_unparsed": raw}


# ---------------------------------------------------------------------------
# Requests through llm_caller. Each takes the call site as a parameter with a
# literal default, so tests/test_llm_routing.py can see which site it names.
# ---------------------------------------------------------------------------

async def _anthropic_request(kwargs: Dict[str, Any], client: Any, call_site: str = "session.generic"):
    from llm_caller import create_message
    return await create_message(call_site, client=client, **kwargs)


async def _openai_request(payload: Dict[str, Any], model: str, base_url: Optional[str],
                          api_key: Optional[str], call_site: str = "session.generic"):
    from llm_caller import openai_raw
    return await openai_raw(call_site, payload, default_model=model, base_url=base_url, api_key=api_key)


async def _ollama_request(payload: Dict[str, Any], model: str, base_url: Optional[str], timeout: float,
                          call_site: str = "session.generic") -> Dict[str, Any]:
    from llm_caller import ollama_raw
    return await ollama_raw(call_site, payload, endpoint="chat", default_model=model,
                            base_url=base_url, timeout=timeout, category="autonomous")


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

CACHE = {"type": "ephemeral"}


def anthropic_messages(history: List[Dict[str, Any]], cache: bool = True) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = []
    for h in history:
        role = h["role"]
        if role == "user":
            msgs.append({"role": "user", "content": [{"type": "text", "text": _user_text(h)}]})
        elif role == "assistant":
            blocks: List[Dict[str, Any]] = [{"type": "text", "text": h["text"]}] if h.get("text") else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c.get("input") or {}}
                       for c in h.get("calls") or []]
            msgs.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "(no reply)"}]})
        elif role == "tool":
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                for r in h["results"]]})
        else:
            raise ValueError(f"unknown history role {role!r}")
    if cache and msgs:
        # Breakpoint on the newest block: the next step reads everything up
        # to here from the cache.
        last = dict(msgs[-1]["content"][-1])
        last["cache_control"] = CACHE
        msgs[-1] = {"role": msgs[-1]["role"], "content": msgs[-1]["content"][:-1] + [last]}
    return msgs


class AnthropicModelClient:
    provider = "anthropic"

    def __init__(self, client: Any = None, call_site: str = "session.generic", cache: bool = True):
        if client is None:
            import anthropic
            client = anthropic.AsyncAnthropic()
        self._client = client
        self.call_site = call_site
        self.cache = cache

    async def create(self, *, model, system, tools, messages, max_tokens) -> ModelReply:
        kwargs: Dict[str, Any] = dict(model=model, max_tokens=max_tokens,
                                      messages=anthropic_messages(messages, self.cache))
        if self.cache:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": CACHE}]
            if tools:
                tools = [dict(t) for t in tools]
                tools[-1]["cache_control"] = CACHE
        else:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        # Model routing (#64): the call site's override, else `model`;
        # llm_caller records the usage (cache reads/writes too) in the ledger.
        response = await _anthropic_request(kwargs, self._client, self.call_site)
        text, calls = "", []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                calls.append({"id": block.id, "name": block.name, "input": block.input})
        usage = response.usage
        return ModelReply(
            text=text, tool_calls=calls, stop_reason=response.stop_reason,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            content=response.content,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )


# ---------------------------------------------------------------------------
# OpenAI (and anything that speaks chat.completions)
# ---------------------------------------------------------------------------

def openai_messages(system: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    for h in history:
        role = h["role"]
        if role == "user":
            msgs.append({"role": "user", "content": _user_text(h)})
        elif role == "assistant":
            m: Dict[str, Any] = {"role": "assistant", "content": h.get("text") or None}
            if h.get("calls"):
                m["tool_calls"] = [{"id": c["id"], "type": "function",
                                    "function": {"name": c["name"],
                                                 "arguments": json.dumps(c.get("input") or {})}}
                                   for c in h["calls"]]
            elif not h.get("text"):
                m["content"] = "(no reply)"
            msgs.append(m)
        elif role == "tool":
            for r in h["results"]:
                msgs.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
        else:
            raise ValueError(f"unknown history role {role!r}")
    return msgs


class OpenAIModelClient:
    provider = "openai"

    def __init__(self, call_site: str = "session.generic", base_url: Optional[str] = None,
                 api_key: Optional[str] = None):
        self.call_site = call_site
        self.base_url = base_url
        self.api_key = api_key

    async def create(self, *, model, system, tools, messages, max_tokens) -> ModelReply:
        payload: Dict[str, Any] = {"model": model, "messages": openai_messages(system, messages),
                                   "max_tokens": max_tokens}
        if tools:
            payload["tools"] = _function_tools(tools)
        completion = await _openai_request(payload, model, self.base_url, self.api_key, self.call_site)
        choice = completion.choices[0]
        message = choice.message
        calls = [{"id": tc.id or f"call_{i}", "name": tc.function.name,
                  "input": _parse_args(tc.function.arguments)}
                 for i, tc in enumerate(message.tool_calls or [])]
        usage = completion.usage
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        prompt = (getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        return ModelReply(
            text=message.content or "", tool_calls=calls, stop_reason=choice.finish_reason,
            input_tokens=prompt - cached,
            output_tokens=(getattr(usage, "completion_tokens", 0) or 0) if usage else 0,
            content=message, cache_read_tokens=cached,
        )


# ---------------------------------------------------------------------------
# Ollama (native /api/chat)
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_NUM_CTX = 32768


def ollama_messages(system: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    for h in history:
        role = h["role"]
        if role == "user":
            msgs.append({"role": "user", "content": _user_text(h)})
        elif role == "assistant":
            m: Dict[str, Any] = {"role": "assistant", "content": h.get("text") or ""}
            if h.get("calls"):
                m["tool_calls"] = [{"function": {"name": c["name"], "arguments": c.get("input") or {}}}
                                   for c in h["calls"]]
            msgs.append(m)
        elif role == "tool":
            for r in h["results"]:
                msgs.append({"role": "tool", "content": r["content"], "tool_name": r["name"]})
        else:
            raise ValueError(f"unknown history role {role!r}")
    return msgs


class OllamaModelClient:
    provider = "ollama"

    def __init__(self, call_site: str = "session.generic", base_url: Optional[str] = None,
                 num_ctx: Optional[int] = None, timeout: float = 900.0):
        self.call_site = call_site
        self.base_url = base_url
        self.num_ctx = num_ctx or int(os.environ.get("AGENT_LOOP_OLLAMA_NUM_CTX", DEFAULT_OLLAMA_NUM_CTX))
        self.timeout = timeout
        self._step = 0

    async def create(self, *, model, system, tools, messages, max_tokens) -> ModelReply:
        payload: Dict[str, Any] = {"model": model, "messages": ollama_messages(system, messages),
                                   "stream": False,
                                   "options": {"num_ctx": self.num_ctx, "num_predict": max_tokens}}
        if tools:
            payload["tools"] = _function_tools(tools)
        data = await _ollama_request(payload, model, self.base_url, self.timeout, self.call_site)
        self._step += 1
        message = data.get("message") or {}
        # Ollama gives tool calls no ids; make ones unique within the turn.
        calls = [{"id": f"call_{self._step}_{i}", "name": tc["function"]["name"],
                  "input": _parse_args(tc["function"].get("arguments"))}
                 for i, tc in enumerate(message.get("tool_calls") or [])]
        return ModelReply(
            text=message.get("content") or "", tool_calls=calls, stop_reason=data.get("done_reason"),
            input_tokens=data.get("prompt_eval_count", 0) or 0,
            output_tokens=data.get("eval_count", 0) or 0,
            content=message,
        )


# ---------------------------------------------------------------------------
# Picking a client
# ---------------------------------------------------------------------------

def model_client_for(call_site: str = "session.generic", default_model: str = "",
                     anthropic_client: Any = None,
                     default_provider: str = "anthropic") -> Tuple[ModelClient, str]:
    """The client and model a turn at `call_site` runs on: the call site's
    admin override if there is one, else `default_provider:default_model`."""
    from llm_config import ModelAssignment, resolve_model
    default = ModelAssignment(default_provider, default_model)
    try:
        assignment = resolve_model(call_site, default) or default
    except Exception as e:  # llm_config unavailable: run the default
        logger.warning(f"[agent_loop] couldn't resolve {call_site}: {e}; running {default_model}")
        assignment = default
    if assignment.provider == "ollama":
        return OllamaModelClient(call_site), assignment.model_id
    if assignment.provider == "openai":
        return OpenAIModelClient(call_site), assignment.model_id
    if assignment.provider != "anthropic":
        logger.warning(f"[agent_loop] unknown provider {assignment.provider!r} for {call_site}; "
                       f"running {default_provider}:{default_model}")
        assignment = default
    return AnthropicModelClient(anthropic_client, call_site), assignment.model_id
