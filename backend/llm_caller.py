"""
Unified LLM Caller

Every LLM call in the backend goes through this module (see
tests/test_llm_routing.py). For each call it:

1. Resolves the model for the call site through llm_config (admin override,
   else the call site's default policy, which is the model it used before).
2. Calls Anthropic, Ollama or OpenAI.
3. Falls back to the assignment's fallback model when the first one fails.
4. Records usage in the token ledger (token_usage_records) with the call
   site name, so spend can be shown per subsystem.

Two entry points:

* call_llm / call_llm_sync: text in, text out (system prompt + user prompt or
  a plain messages list). Works on every provider.
* create_message / create_message_sync: Anthropic Messages-API shaped
  (kwargs passed through, returns an anthropic Message). Use it where a call
  site needs tools, images, or reads the Message object. When an admin assigns
  a non-Claude model, a text-only request is translated and the reply is
  wrapped as a Message; a request with tools or images stays on the call
  site's default (logged), since only Claude runs those here.

record_usage() is for code that must keep its own client (chat).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Optional

import httpx

from llm_config import CALL_SITES, ModelAssignment, resolve_model, LLMConfigManager

logger = logging.getLogger("cass-vessel")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_ENABLED = os.environ.get("OPENAI_ENABLED", "false").lower() == "true"


def _ollama_allowed() -> bool:
    """OLLAMA_ENABLED=false in the environment turns every routed Ollama call
    into an error (so a fallback runs), as the old llm_caller did. Unset
    counts as allowed: an admin's Ollama assignment runs. Defaults that depend
    on OLLAMA_ENABLED (config's default is off) live in llm_config policies."""
    return os.environ.get("OLLAMA_ENABLED", "true").lower() == "true"


class LLMResponse:
    """Response from an LLM call."""

    def __init__(
        self,
        content: str,
        provider: str,
        model_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: Optional[str] = None,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        raw: Any = None,
        call_site: Optional[str] = None,
        rejected: bool = False,
    ):
        self.content = content
        self.provider = provider
        self.model_id = model_id
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.error = error
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens
        self.raw = raw
        self.call_site = call_site
        self.rejected = rejected  # content came back but the caller's accept() said no

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)

    def __repr__(self):
        return (f"LLMResponse({self.provider}:{self.model_id}, {len(self.content or '')} chars, "
                f"error={self.error!r})")


# ---------------------------------------------------------------------------
# Resolution and the ledger
# ---------------------------------------------------------------------------

def _category_for(call_site: str, category: Optional[str]) -> str:
    if category:
        return category
    site = CALL_SITES.get(call_site)
    if site and site.category:
        return site.category
    return call_site.split(".")[0]


def record_usage(
    call_site: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    duration_ms: int = 0,
    category: Optional[str] = None,
    operation: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tool_name: Optional[str] = None,
):
    """Write one row to the token ledger for this call site. Never raises in production."""
    try:
        from token_tracker import TokenUsageTracker
        return TokenUsageTracker().record(
            category=_category_for(call_site, category),
            operation=operation or call_site,
            provider=provider,
            model=model,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            cache_read_tokens=cache_read_tokens or 0,
            cache_write_tokens=cache_write_tokens or 0,
            duration_ms=duration_ms,
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=tool_name,
            call_site=call_site,
        )
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, f"llm usage record ({call_site})")
        return None


def _record_response(call_site: str, resp: "LLMResponse", started: float, ledger: dict):
    if resp.error is not None:
        return
    record_usage(
        call_site, resp.provider, resp.model_id,
        input_tokens=resp.input_tokens + resp.cache_read_tokens,
        output_tokens=resp.output_tokens,
        cache_read_tokens=resp.cache_read_tokens,
        cache_write_tokens=resp.cache_write_tokens,
        duration_ms=int((time.time() - started) * 1000),
        **ledger,
    )


def _attempts(assignment: Optional[ModelAssignment]) -> list:
    if assignment is None:
        return []
    out = [(assignment.provider, assignment.model_id)]
    if assignment.fallback_provider and assignment.fallback_model_id:
        out.append((assignment.fallback_provider, assignment.fallback_model_id))
    return out


def _check_site(call_site: str):
    if call_site not in CALL_SITES:
        # Unregistered names still run on the caller's default, but belong in
        # llm_config.CALL_SITES (tests/test_llm_routing.py enforces it).
        logger.warning(f"llm_caller: call site {call_site!r} is not registered in llm_config.CALL_SITES")


# ---------------------------------------------------------------------------
# Provider plumbing (one place; tests/fakes/llm.py patches the SDKs and the
# two _ollama_request functions)
# ---------------------------------------------------------------------------

def _anthropic_client(is_async: bool, api_key: Optional[str] = None):
    """A fresh SDK client per call, as the call sites made before routing."""
    import anthropic
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    return anthropic.AsyncAnthropic(api_key=key) if is_async else anthropic.Anthropic(api_key=key)


def _openai_client(is_async: bool, api_key: Optional[str] = None):
    import openai
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return openai.AsyncOpenAI(api_key=key) if is_async else openai.OpenAI(api_key=key)


def _ollama_url(base_url: Optional[str]) -> str:
    if base_url:
        return base_url
    try:
        import config
        return config.OLLAMA_BASE_URL
    except Exception:
        return OLLAMA_BASE_URL


async def _ollama_request(base_url: str, endpoint: str, payload: dict, timeout: float) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base_url}/api/{endpoint}", json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def _ollama_request_sync(base_url: str, endpoint: str, payload: dict, timeout: float) -> dict:
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/api/{endpoint}", json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def _flatten(content) -> str:
    """Anthropic content (str or list of blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type", "text") == "text":
                parts.append(block.get("text", ""))
        else:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts)


class _Request:
    """A provider-neutral text request."""

    def __init__(self, system_prompt=None, user_prompt="", messages=None, max_tokens=1000,
                 temperature=None, timeout=None, ollama_options=None, ollama_extra=None,
                 ollama_base_url=None, json_mode=False, anthropic_kwargs=None, client=None,
                 anthropic_api_key=None, openai_api_key=None):
        self.system_prompt = system_prompt
        self.use_chat = messages is not None
        self.messages = list(messages) if messages is not None else [{"role": "user", "content": user_prompt}]
        self.user_prompt = user_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout if timeout is not None else 120.0
        self.ollama_options = ollama_options
        self.ollama_extra = ollama_extra or {}
        self.ollama_base_url = ollama_base_url
        self.json_mode = json_mode
        self.anthropic_kwargs = anthropic_kwargs or {}
        self.client = client
        self.anthropic_api_key = anthropic_api_key
        self.openai_api_key = openai_api_key

    def anthropic(self, model_id: str) -> dict:
        kw = {"model": model_id, "max_tokens": self.max_tokens, "messages": self.messages}
        if self.system_prompt:
            kw["system"] = self.system_prompt
        if self.temperature is not None:
            kw["temperature"] = self.temperature
        kw.update(self.anthropic_kwargs)
        return kw

    def _chat_messages(self) -> list:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": _flatten(self.system_prompt)})
        messages.extend({"role": m["role"], "content": _flatten(m["content"])} for m in self.messages)
        return messages

    def openai(self, model_id: str) -> dict:
        kw = {"model": model_id, "messages": self._chat_messages()}
        if self.max_tokens:
            kw["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            kw["temperature"] = self.temperature
        if self.json_mode:
            kw["response_format"] = {"type": "json_object"}
        return kw

    def ollama(self, model_id: str) -> tuple:
        if self.ollama_options is not None:
            options = dict(self.ollama_options)
        else:
            options = {"num_predict": self.max_tokens}
            if self.temperature is not None:
                options["temperature"] = self.temperature
        if self.use_chat:
            payload = {"model": model_id, "messages": self._chat_messages(), "stream": False}
            endpoint = "chat"
        else:
            payload = {"model": model_id, "prompt": self.user_prompt, "stream": False}
            if self.system_prompt:
                payload["system"] = _flatten(self.system_prompt)
            endpoint = "generate"
        if options:
            payload["options"] = options
        if self.json_mode:
            payload["format"] = "json"
        payload.update(self.ollama_extra)
        return endpoint, payload


def _anthropic_to_response(msg, model_id: str) -> LLMResponse:
    text = "".join(getattr(b, "text", "") or "" for b in (msg.content or [])
                   if getattr(b, "type", "text") == "text")
    usage = getattr(msg, "usage", None)
    return LLMResponse(
        content=text, provider="anthropic", model_id=model_id,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        raw=msg,
    )


def _openai_to_response(completion, model_id: str) -> LLMResponse:
    usage = getattr(completion, "usage", None)
    return LLMResponse(
        content=completion.choices[0].message.content or "", provider="openai", model_id=model_id,
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        raw=completion,
    )


def _ollama_to_response(data: dict, model_id: str) -> LLMResponse:
    text = data.get("response")
    if text is None:
        text = (data.get("message") or {}).get("content", "")
    return LLMResponse(
        content=text or "", provider="ollama", model_id=model_id,
        input_tokens=data.get("prompt_eval_count", 0) or 0,
        output_tokens=data.get("eval_count", 0) or 0,
        raw=data,
    )


async def _call_provider(provider: str, model_id: str, req: _Request) -> LLMResponse:
    try:
        if provider == "anthropic":
            client = req.client or _anthropic_client(True, req.anthropic_api_key)
            msg = await client.messages.create(**req.anthropic(model_id))
            return _anthropic_to_response(msg, model_id)
        if provider == "ollama":
            if not _ollama_allowed():
                return LLMResponse("", provider, model_id, error="Ollama not enabled (OLLAMA_ENABLED=false)")
            endpoint, payload = req.ollama(model_id)
            data = await _ollama_request(_ollama_url(req.ollama_base_url), endpoint, payload, req.timeout)
            return _ollama_to_response(data, model_id)
        if provider == "openai":
            completion = await _openai_client(True, req.openai_api_key).chat.completions.create(**req.openai(model_id))
            return _openai_to_response(completion, model_id)
        return LLMResponse("", provider, model_id, error=f"Unknown provider: {provider}")
    except Exception as e:
        return LLMResponse("", provider, model_id, error=f"{type(e).__name__}: {e}")


def _call_provider_sync(provider: str, model_id: str, req: _Request) -> LLMResponse:
    try:
        if provider == "anthropic":
            client = req.client or _anthropic_client(False, req.anthropic_api_key)
            msg = client.messages.create(**req.anthropic(model_id))
            return _anthropic_to_response(msg, model_id)
        if provider == "ollama":
            if not _ollama_allowed():
                return LLMResponse("", provider, model_id, error="Ollama not enabled (OLLAMA_ENABLED=false)")
            endpoint, payload = req.ollama(model_id)
            data = _ollama_request_sync(_ollama_url(req.ollama_base_url), endpoint, payload, req.timeout)
            return _ollama_to_response(data, model_id)
        if provider == "openai":
            completion = _openai_client(False, req.openai_api_key).chat.completions.create(**req.openai(model_id))
            return _openai_to_response(completion, model_id)
        return LLMResponse("", provider, model_id, error=f"Unknown provider: {provider}")
    except Exception as e:
        return LLMResponse("", provider, model_id, error=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# call_llm: text in, text out
# ---------------------------------------------------------------------------

_REQ_KEYS = ("messages", "ollama_options", "ollama_extra", "ollama_base_url", "json_mode",
             "anthropic_kwargs", "client", "anthropic_api_key", "openai_api_key")
_LEDGER_KEYS = ("category", "operation", "conversation_id", "user_id")


def _skipped(call_site: str) -> LLMResponse:
    return LLMResponse("", "none", "", error=f"no model assigned to {call_site} (its default skips the call)",
                       call_site=call_site)


def _finish(call_site, resp, accept):
    resp.call_site = call_site
    if resp.error is not None:
        logger.warning(f"[llm:{call_site}] {resp.provider}:{resp.model_id} failed: {resp.error}")
        return resp, False
    if accept is not None and not accept(resp.content):
        resp.rejected = True
        return resp, False
    return resp, True


def _split(kwargs: dict):
    req_kw = {k: kwargs.pop(k) for k in _REQ_KEYS if k in kwargs}
    ledger = {k: kwargs.pop(k, None) for k in _LEDGER_KEYS}
    default = kwargs.pop("default", None)
    accept = kwargs.pop("accept", None)
    if kwargs:
        raise TypeError(f"call_llm got unexpected arguments: {sorted(kwargs)}")
    return req_kw, ledger, default, accept


async def call_llm(
    call_site: str,
    system_prompt: Optional[str] = None,
    user_prompt: str = "",
    max_tokens: int = 1000,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> LLMResponse:
    """
    Make a text LLM call with the model llm_config assigns to `call_site`.

    Keyword options:
      default          ModelAssignment the call site runs when nobody set an
                       override and the model is chosen at runtime (otherwise
                       the registered policy in llm_config applies)
      accept(text)     return False to reject a reply and try the fallback
      messages         plain [{"role","content"}] list instead of user_prompt
      ollama_options   sent verbatim as Ollama's options (else num_predict and
                       temperature come from max_tokens/temperature)
      ollama_extra, ollama_base_url, json_mode, anthropic_kwargs,
      client (an anthropic client to reuse), anthropic_api_key, openai_api_key
      category, operation, conversation_id, user_id   ledger fields

    `timeout` applies to Ollama/OpenAI HTTP calls (Claude keeps the SDK's).
    Never raises for provider errors: check `.success` / `.error`.
    """
    req_kw, ledger, default, accept = _split(kwargs)
    _check_site(call_site)
    assignment = resolve_model(call_site, default)
    attempts = _attempts(assignment)
    if not attempts:
        return _skipped(call_site)
    req = _Request(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature,
                   timeout=timeout, **req_kw)
    resp = None
    for provider, model_id in attempts:
        started = time.time()
        resp = await _call_provider(provider, model_id, req)
        _record_response(call_site, resp, started, ledger)
        resp, ok = _finish(call_site, resp, accept)
        if ok:
            return resp
    return resp


def call_llm_sync(
    call_site: str,
    system_prompt: Optional[str] = None,
    user_prompt: str = "",
    max_tokens: int = 1000,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> LLMResponse:
    """Synchronous call_llm (same arguments), with blocking clients."""
    req_kw, ledger, default, accept = _split(kwargs)
    _check_site(call_site)
    assignment = resolve_model(call_site, default)
    attempts = _attempts(assignment)
    if not attempts:
        return _skipped(call_site)
    req = _Request(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature,
                   timeout=timeout, **req_kw)
    resp = None
    for provider, model_id in attempts:
        started = time.time()
        resp = _call_provider_sync(provider, model_id, req)
        _record_response(call_site, resp, started, ledger)
        resp, ok = _finish(call_site, resp, accept)
        if ok:
            return resp
    return resp


# ---------------------------------------------------------------------------
# create_message: Anthropic Messages-API shaped
# ---------------------------------------------------------------------------

def _needs_claude(kwargs: dict) -> Optional[str]:
    """Why this request can only run on Claude here (None if it is plain text)."""
    if kwargs.get("tools") or kwargs.get("tool_choice"):
        return "tools"
    for m in kwargs.get("messages") or []:
        content = m.get("content") if isinstance(m, dict) else None
        if isinstance(content, list):
            for block in content:
                t = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if t not in (None, "text"):
                    return f"{t} blocks"
    return None


def _as_message(resp: LLMResponse):
    """Wrap a non-Claude text reply as an anthropic Message."""
    from anthropic.types import Message, TextBlock, Usage
    return Message(
        id=f"msg_routed_{uuid.uuid4().hex[:12]}", type="message", role="assistant", model=resp.model_id,
        content=[TextBlock(type="text", text=resp.content or "")],
        stop_reason="end_turn", stop_sequence=None,
        usage=Usage(input_tokens=resp.input_tokens, output_tokens=resp.output_tokens),
    )


def plan_message(call_site: str, model: Optional[str] = None,
                 default: Optional[ModelAssignment] = None, request: Optional[dict] = None) -> ModelAssignment:
    """The assignment a Messages-API request for `call_site` will run on."""
    _check_site(call_site)
    if default is None and model:
        default = ModelAssignment("anthropic", model)
    manager = LLMConfigManager()
    assignment = manager.resolve(call_site, default)
    if assignment is None:
        raise RuntimeError(f"No model assigned to call site {call_site}")
    reason = _needs_claude(request or {})
    if reason:
        if assignment.provider != "anthropic":
            fallback = manager.default_for(call_site, default)
            if fallback is None or fallback.provider != "anthropic":
                raise RuntimeError(f"{call_site}: request uses {reason}; only Claude can run it")
            logger.warning(f"[llm:{call_site}] assigned {assignment.provider}:{assignment.model_id} "
                           f"but the request uses {reason}; running the default {fallback.model_id}")
            assignment = fallback
        if assignment.fallback_provider and assignment.fallback_provider != "anthropic":
            assignment = ModelAssignment("anthropic", assignment.model_id)
    return assignment


def _text_request(kwargs: dict) -> _Request:
    return _Request(
        system_prompt=_flatten(kwargs.get("system")) or None,
        messages=list(kwargs.get("messages") or []),
        max_tokens=kwargs.get("max_tokens", 1024),
        temperature=kwargs.get("temperature"),
    )


async def create_message(
    call_site: str,
    *,
    model: Optional[str] = None,
    default: Optional[ModelAssignment] = None,
    client: Any = None,
    category: Optional[str] = None,
    operation: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs,
):
    """
    anthropic `messages.create(**kwargs)` for `call_site`, with the model from
    llm_config. `model` is the call site's own default (today's model) when it
    is chosen at runtime. `client` (an anthropic client of the matching
    sync/async kind) or `api_key` set how Claude is reached. Raises like the
    SDK when the last attempt fails.
    """
    kwargs.pop("model", None)
    assignment = plan_message(call_site, model, default, kwargs)
    ledger = dict(category=category, operation=operation, conversation_id=conversation_id,
                  user_id=user_id, tool_name=tool_name)
    attempts = _attempts(assignment)
    last_error = None
    for i, (provider, model_id) in enumerate(attempts):
        started = time.time()
        if provider == "anthropic":
            c = client or _anthropic_client(True, api_key)
            try:
                msg = await c.messages.create(model=model_id, **kwargs)
            except Exception as e:
                last_error = e
                if i + 1 < len(attempts):
                    logger.warning(f"[llm:{call_site}] {provider}:{model_id} failed: {e}; trying fallback")
                    continue
                raise
            _record_response(call_site, _anthropic_to_response(msg, model_id), started, ledger)
            return msg
        resp = await _call_provider(provider, model_id, _text_request(kwargs))
        _record_response(call_site, resp, started, ledger)
        if resp.error is None:
            return _as_message(resp)
        last_error = RuntimeError(resp.error)
        logger.warning(f"[llm:{call_site}] {provider}:{model_id} failed: {resp.error}")
    raise last_error or RuntimeError(f"{call_site}: no model to call")


def create_message_sync(
    call_site: str,
    *,
    model: Optional[str] = None,
    default: Optional[ModelAssignment] = None,
    client: Any = None,
    category: Optional[str] = None,
    operation: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs,
):
    """Synchronous create_message."""
    kwargs.pop("model", None)
    assignment = plan_message(call_site, model, default, kwargs)
    ledger = dict(category=category, operation=operation, conversation_id=conversation_id,
                  user_id=user_id, tool_name=tool_name)
    attempts = _attempts(assignment)
    last_error = None
    for i, (provider, model_id) in enumerate(attempts):
        started = time.time()
        if provider == "anthropic":
            c = client or _anthropic_client(False, api_key)
            try:
                msg = c.messages.create(model=model_id, **kwargs)
            except Exception as e:
                last_error = e
                if i + 1 < len(attempts):
                    logger.warning(f"[llm:{call_site}] {provider}:{model_id} failed: {e}; trying fallback")
                    continue
                raise
            _record_response(call_site, _anthropic_to_response(msg, model_id), started, ledger)
            return msg
        resp = _call_provider_sync(provider, model_id, _text_request(kwargs))
        _record_response(call_site, resp, started, ledger)
        if resp.error is None:
            return _as_message(resp)
        last_error = RuntimeError(resp.error)
        logger.warning(f"[llm:{call_site}] {provider}:{model_id} failed: {resp.error}")
    raise last_error or RuntimeError(f"{call_site}: no model to call")


# ---------------------------------------------------------------------------
# ollama_chat_raw: for loops that speak Ollama's own /api/chat format (tools)
# ---------------------------------------------------------------------------

async def ollama_raw(
    call_site: str,
    payload: dict,
    *,
    endpoint: str = "chat",
    default_model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 120.0,
    category: Optional[str] = None,
    operation: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """POST a native Ollama request for `call_site` and return Ollama's JSON.

    For code that needs Ollama's own request/response shape (tool calls on
    /api/chat). The model comes from llm_config when it assigns an Ollama
    model; any other assignment can't take this request, so the call site's
    default Ollama model runs (logged). Raises on HTTP errors.
    """
    _check_site(call_site)
    default = ModelAssignment("ollama", default_model or payload.get("model"))
    assignment = resolve_model(call_site, default) or default
    if assignment.provider != "ollama":
        logger.warning(f"[llm:{call_site}] assigned {assignment.provider}:{assignment.model_id} "
                       f"but this request is Ollama-native; running {default.model_id}")
        assignment = default
    body = dict(payload)
    body["model"] = assignment.model_id
    started = time.time()
    data = await _ollama_request(_ollama_url(base_url), endpoint, body, timeout)
    resp = _ollama_to_response(data, assignment.model_id)
    _record_response(call_site, resp, started, dict(category=category, operation=operation,
                                                     conversation_id=conversation_id, user_id=user_id))
    return data
