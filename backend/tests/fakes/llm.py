"""
Scriptable fake LLM for tests.

One object replaces every LLM path Cass uses in production, so no test can
reach a real model:

  * anthropic.AsyncAnthropic().messages.create / .stream   (CassAgentClient chat,
    dreams, GenericSessionRunner, goal planner, title generation, ...)
  * anthropic.Anthropic().messages.create / .stream        (journals, art study,
    janet, legacy runners, ...)
  * llm_caller._call_model                                 (Grimoire ASK/RATE/
    REFLECT/GENERATE and other per-call-site LLM calls; it uses raw httpx)
  * openai chat.completions.create (sync + async)          (OpenAI provider)

It patches the SDK *resource classes*, so every client instance is covered no
matter where or when it was constructed.

Usage (via the `fake_llm` fixture in tests/conftest.py):

    fake_llm.queue_text("Hello Kohl")
    fake_llm.queue_tool_use("lookup_person", {"name": "Kohl"}, text="Let me check.")
    ...
    req = fake_llm.calls[0]
    assert "Kohl" in req.system_text
    assert "lookup_person" in req.tool_names

When the queue is empty the fake answers with `default_text` (so background
calls like title generation don't crash a test). Set `strict=True` to make an
unexpected call fail the test instead.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

_ids = itertools.count(1)


@dataclass
class ScriptedResponse:
    """One canned model reply: optional text plus zero or more tool calls."""
    text: str = ""
    tool_uses: List[Dict[str, Any]] = field(default_factory=list)  # [{"id","name","input"}]
    input_tokens: int = 10
    output_tokens: int = 5
    stop_reason: Optional[str] = None  # derived when None

    @property
    def effective_stop_reason(self) -> str:
        if self.stop_reason:
            return self.stop_reason
        return "tool_use" if self.tool_uses else "end_turn"


@dataclass
class RecordedCall:
    """Everything a caller sent to the model, for assertions."""
    source: str                 # "anthropic.async", "anthropic.sync", "llm_caller", "openai.async", ...
    kwargs: Dict[str, Any]
    response: ScriptedResponse

    @property
    def model(self) -> Optional[str]:
        return self.kwargs.get("model")

    @property
    def system(self) -> Any:
        return self.kwargs.get("system")

    @property
    def system_text(self) -> str:
        """System prompt flattened to a string (handles block lists)."""
        system = self.system
        if system is None:
            return ""
        if isinstance(system, str):
            return system
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in system)

    @property
    def messages(self) -> List[Dict[str, Any]]:
        return list(self.kwargs.get("messages") or [])

    @property
    def tools(self) -> List[Dict[str, Any]]:
        return list(self.kwargs.get("tools") or [])

    @property
    def tool_names(self) -> List[str]:
        names = []
        for tool in self.tools:
            if "name" in tool:
                names.append(tool["name"])
            elif "function" in tool:  # OpenAI format
                names.append(tool["function"].get("name"))
        return names


class FakeLLM:
    def __init__(self, default_text: str = "OK", strict: bool = False):
        self.default_text = default_text
        self.strict = strict
        self._queue: List[ScriptedResponse] = []
        self.calls: List[RecordedCall] = []
        # Optional hook: fn(source, kwargs) -> ScriptedResponse | None, checked before the queue.
        self.responder: Optional[Callable[[str, Dict[str, Any]], Optional[ScriptedResponse]]] = None

    # ----- scripting -------------------------------------------------------

    def queue(self, response: ScriptedResponse) -> "FakeLLM":
        self._queue.append(response)
        return self

    def queue_text(self, text: str, **kw) -> "FakeLLM":
        return self.queue(ScriptedResponse(text=text, **kw))

    def queue_json(self, obj: Any, **kw) -> "FakeLLM":
        return self.queue_text(json.dumps(obj), **kw)

    def queue_tool_use(self, name: str, tool_input: Optional[dict] = None, text: str = "",
                       tool_id: Optional[str] = None, **kw) -> "FakeLLM":
        tool = {"id": tool_id or f"toolu_fake_{next(_ids)}", "name": name, "input": tool_input or {}}
        return self.queue(ScriptedResponse(text=text, tool_uses=[tool], **kw))

    @property
    def pending(self) -> int:
        return len(self._queue)

    # ----- accounting ------------------------------------------------------

    @property
    def total_input_tokens(self) -> int:
        return sum(c.response.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.response.output_tokens for c in self.calls)

    def calls_from(self, prefix: str) -> List[RecordedCall]:
        return [c for c in self.calls if c.source.startswith(prefix)]

    # ----- core ------------------------------------------------------------

    def _next(self, source: str, kwargs: Dict[str, Any]) -> ScriptedResponse:
        response = self.responder(source, kwargs) if self.responder else None
        if response is None:
            if self._queue:
                response = self._queue.pop(0)
            elif self.strict:
                raise AssertionError(f"FakeLLM: unexpected {source} call (queue empty, strict=True)")
            else:
                response = ScriptedResponse(text=self.default_text)
        recorded = dict(kwargs)
        # Callers keep appending to the same messages list (tool chains), so
        # snapshot it to record what was actually sent at this call.
        if isinstance(recorded.get("messages"), list):
            recorded["messages"] = list(recorded["messages"])
        self.calls.append(RecordedCall(source=source, kwargs=recorded, response=response))
        return response


# ---------------------------------------------------------------------------
# Response builders (SDK-shaped objects so production parsing code runs as-is)
# ---------------------------------------------------------------------------

def to_anthropic_message(resp: ScriptedResponse, model: str = "fake-model"):
    from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

    content = []
    if resp.text:
        content.append(TextBlock(type="text", text=resp.text))
    for tool in resp.tool_uses:
        content.append(ToolUseBlock(type="tool_use", id=tool["id"], name=tool["name"], input=tool["input"]))
    return Message(
        id=f"msg_fake_{next(_ids)}",
        type="message",
        role="assistant",
        model=model or "fake-model",
        content=content,
        stop_reason=resp.effective_stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=resp.input_tokens, output_tokens=resp.output_tokens),
    )


def to_openai_completion(resp: ScriptedResponse, model: str = "fake-model"):
    from openai.types.chat import ChatCompletion

    tool_calls = [
        {"id": t["id"], "type": "function",
         "function": {"name": t["name"], "arguments": json.dumps(t["input"])}}
        for t in resp.tool_uses
    ] or None
    return ChatCompletion.model_validate({
        "id": f"chatcmpl_fake_{next(_ids)}",
        "object": "chat.completion",
        "created": 0,
        "model": model or "fake-model",
        "choices": [{
            "index": 0,
            "finish_reason": "tool_calls" if tool_calls else "stop",
            "message": {"role": "assistant", "content": resp.text or None, "tool_calls": tool_calls},
        }],
        "usage": {"prompt_tokens": resp.input_tokens, "completion_tokens": resp.output_tokens,
                  "total_tokens": resp.input_tokens + resp.output_tokens},
    })


class _FakeStream:
    """Minimal stand-in for anthropic's MessageStream (text_stream + final message)."""

    def __init__(self, message):
        self._message = message
        self._text = "".join(getattr(b, "text", "") for b in message.content)

    # async side
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        text = self._text

        class _Iter:
            def __aiter__(self_inner):
                self_inner._done = False
                return self_inner

            async def __anext__(self_inner):
                if self_inner._done:
                    raise StopAsyncIteration
                self_inner._done = True
                return text

            def __iter__(self_inner):
                return iter([text])

        return _Iter()

    async def get_final_message(self):
        return self._message

    # sync side
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def install(fake: FakeLLM, monkeypatch) -> FakeLLM:
    """Patch every LLM entry point to answer from `fake`. Undone by monkeypatch."""
    from anthropic.resources.messages import AsyncMessages, Messages

    async def async_create(self, **kwargs):
        return to_anthropic_message(fake._next("anthropic.async", kwargs), kwargs.get("model"))

    def sync_create(self, **kwargs):
        return to_anthropic_message(fake._next("anthropic.sync", kwargs), kwargs.get("model"))

    def async_stream(self, **kwargs):
        return _FakeStream(to_anthropic_message(fake._next("anthropic.async.stream", kwargs), kwargs.get("model")))

    def sync_stream(self, **kwargs):
        return _FakeStream(to_anthropic_message(fake._next("anthropic.sync.stream", kwargs), kwargs.get("model")))

    monkeypatch.setattr(AsyncMessages, "create", async_create)
    monkeypatch.setattr(Messages, "create", sync_create)
    monkeypatch.setattr(AsyncMessages, "stream", async_stream)
    monkeypatch.setattr(Messages, "stream", sync_stream)

    # llm_caller talks to Anthropic/Ollama/OpenAI with raw httpx, so patch its
    # single dispatch point instead of the network layer.
    try:
        import llm_caller

        async def fake_call_model(provider, model_id, system_prompt, user_prompt,
                                  max_tokens, temperature, timeout):
            kwargs = {"provider": provider, "model": model_id, "system": system_prompt,
                      "messages": [{"role": "user", "content": user_prompt}],
                      "max_tokens": max_tokens, "temperature": temperature}
            resp = fake._next("llm_caller", kwargs)
            return llm_caller.LLMResponse(
                content=resp.text, provider=provider, model_id=model_id,
                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            )

        monkeypatch.setattr(llm_caller, "_call_model", fake_call_model)
    except ImportError:
        pass

    try:
        from openai.resources.chat.completions import AsyncCompletions, Completions

        async def openai_async_create(self, **kwargs):
            return to_openai_completion(fake._next("openai.async", kwargs), kwargs.get("model"))

        def openai_sync_create(self, **kwargs):
            return to_openai_completion(fake._next("openai.sync", kwargs), kwargs.get("model"))

        monkeypatch.setattr(AsyncCompletions, "create", openai_async_create)
        monkeypatch.setattr(Completions, "create", openai_sync_create)
    except ImportError:
        pass

    return fake
