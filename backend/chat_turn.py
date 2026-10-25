"""
One chat turn, shared by every chat entry point (issues #57, #70).

WebSocket, the mobile relay, POST /chat, Home Assistant and Discord each
used to assemble their own turn: different prompts, different tool
dispatchers, some with no tag processing and some with no tool loop. They
now call run_chat_turn(), which does the same four steps for all of them:

1. context: build_continuous_context (in a worker thread: semantic retrieval
   is synchronous Chroma/embedding work and blocked the event loop, #85) plus
   the conversation's recent messages;
2. the model call with the shared tool loop (execute_tool_batch over
   TOOL_EXECUTORS, a tool that raises becomes an error result, capped at
   CHAT_MAX_TOOL_ITERATIONS unless the entry point passes a lower cap);
3. finalize_chat_turn: marks, symbols, interests and inline tags stripped
   and stored; the exchange stored in ChromaDB and SQLite; token usage
   recorded; title and summary scheduled;
4. a cross-context behavioral sample (testing/cross_context_analyzer).

Entry points keep what is genuinely theirs: how they authenticate and pick a
conversation, how they report progress, and the shape of their response.

This is not the agent loop (agent_loop/, behind the `agent_loop` lever).
That cutover waits on the Tier 3 comparison (#65); this moves the remaining
chat entry points onto the pipeline the WebSocket already runs.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

ProgressFn = Callable[[Dict[str, Any]], Awaitable[None]]


class NoLLMClient(RuntimeError):
    """The selected provider has no client (e.g. anthropic not installed)."""


@dataclass
class ChatTurnResult:
    clean_text: str
    raw_response: str
    animations: List[Dict]
    tool_uses: List[Dict]  # tool calls left pending when the turn ended (cap hit)
    conversation_id: Optional[str]
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    provider: str
    model: str
    tool_iterations: int
    generated_images: List[Dict]
    memory_used: bool
    # True when the tool cap ended the turn while the model still wanted a
    # tool: clean_text is then whatever came with that tool call ("Let me
    # check..."), not an answer.
    hit_tool_cap: bool = False
    marks: List[Any] = field(default_factory=list)
    extracted: Dict[str, Any] = field(default_factory=dict)


def _select_client(provider: Optional[str]):
    """(client, provider label, model) for this turn.

    provider=None follows the active provider (/settings/llm-provider), as the
    WebSocket always has. "anthropic" pins the turn to the Anthropic client.
    Re-read every turn so a provider switch or client re-init applies at once.
    """
    from config import DEFAULT_SESSION_MODEL
    from websocket_handlers import (
        _state, LLM_PROVIDER_LOCAL, LLM_PROVIDER_OPENAI, LLM_PROVIDER_ANTHROPIC,
    )

    agent_client = _state["agent_client"]
    openai_client = _state["openai_client"]
    ollama_client = _state["ollama_client"]
    active = provider or _state["current_llm_provider"]

    if provider == LLM_PROVIDER_ANTHROPIC:
        if agent_client:
            return agent_client, "anthropic", getattr(agent_client, "model", DEFAULT_SESSION_MODEL)
        raise NoLLMClient("No Anthropic client available (is the anthropic package installed?)")

    # The WebSocket's selection, unchanged: a provider whose client is
    # missing falls through to Anthropic.
    if active == LLM_PROVIDER_LOCAL and ollama_client:
        return ollama_client, "local", ollama_client.model
    if active == LLM_PROVIDER_OPENAI and openai_client:
        return openai_client, "openai", getattr(openai_client, "model", "gpt-4o")
    if _state["use_agent_sdk"] and agent_client:
        return agent_client, "anthropic", getattr(agent_client, "model", DEFAULT_SESSION_MODEL)
    raise NoLLMClient(f"No LLM client available for provider {active!r}")


_PROVIDER_LABELS = {"local": "local model", "openai": "OpenAI", "anthropic": "Claude"}


def _record_cross_context_sample(clean_text, user_message, tool_names, conversation_id):
    """Best-effort behavioral sample (POST /chat used to be the only caller)."""
    try:
        import main_sdk
        analyzer = getattr(main_sdk, "cross_context_analyzer", None)
        if analyzer is None:
            return
        classification = analyzer.classify_context(text=clean_text, user_message=user_message)
        markers = analyzer.extract_behavioral_markers(
            response=clean_text, tool_usage=tool_names or None)
        analyzer.record_sample(
            context=classification.primary_context,
            markers=markers,
            conversation_id=conversation_id,
        )
    except Exception as e:  # never fail a turn over analytics
        print(f"[ChatTurn] Cross-context sample failed: {e}")


async def run_chat_turn(
    *,
    user_message: str,
    conversation_id: Optional[str],
    user_id: Optional[str],
    model_message: Optional[str] = None,
    project_id: Optional[str] = None,
    image: Optional[str] = None,
    image_media_type: Optional[str] = None,
    speaker_recognition=None,
    include_memory: bool = True,
    context_scope: str = "private",
    system_addendum: Optional[str] = None,
    provider: Optional[str] = None,
    tool_cap: Optional[int] = None,
    progress: Optional[ProgressFn] = None,
    memory_metadata: Optional[Dict[str, Any]] = None,
    generate_title: bool = True,
    extra_send_kwargs: Optional[Dict[str, Any]] = None,
    websocket=None,
) -> ChatTurnResult:
    """Run one chat turn and persist it. See the module docstring.

    user_message: what is stored (conversation, memory) and searched with.
    model_message: what the model sees as the user turn, when an entry point
        adds context of its own (HA home state, the Discord channel line).
        Defaults to user_message.
    include_memory: False skips semantic retrieval (POST /chat's flag).
    context_scope: "private" or "public" (continuous_context.CONTEXT_SCOPES).
        Discord uses "public": its replies are posted where others read them.
    system_addendum: appended to the continuous system prompt (Discord's
        "you are on Discord" guidance).
    provider: None follows the active provider; "anthropic" pins it.
    tool_cap: lower cap on tool iterations for this entry point (HA).
    progress: async callback receiving WebSocket-style frames
        ({"type": "thinking"|"debug", ...}).
    """
    from continuous_context import build_continuous_context, get_recent_messages_for_continuous
    from websocket_handlers import (
        _state, mark_user_activity, execute_tools_safely, extract_generated_images,
        max_tool_iterations, finalize_chat_turn,
    )

    async def emit(frame: Dict[str, Any]) -> None:
        if progress is not None:
            frame.setdefault("timestamp", datetime.now().isoformat())
            await progress(frame)

    memory = _state["memory"]
    conversation_manager = _state["conversation_manager"]
    user_manager = _state["user_manager"]
    daemon_id = _state["daemon_id"]
    thread_manager = _state.get("thread_manager")
    question_manager = _state.get("question_manager")
    if daemon_id and (thread_manager is None or question_manager is None):
        from memory import ThreadManager, OpenQuestionManager
        thread_manager = thread_manager or ThreadManager(daemon_id)
        question_manager = question_manager or OpenQuestionManager(daemon_id)

    # A person is talking: idle-only background jobs should wait.
    mark_user_activity()

    # Pick the client before spending time on retrieval.
    turn_client, response_provider, response_model = _select_client(provider)

    # 1. Context. Worker thread: retrieval blocked the event loop (#85).
    continuous_ctx = await asyncio.to_thread(
        build_continuous_context,
        user_id=user_id,
        conversation_id=conversation_id,
        user_manager=user_manager,
        thread_manager=thread_manager,
        question_manager=question_manager,
        conversation_manager=conversation_manager,
        daemon_name="Cass",
        daemon_id=daemon_id,
        memory=memory if include_memory else None,
        query=user_message if include_memory else None,
        speaker_recognition=speaker_recognition,
        scope=context_scope,
    )
    system_prompt = continuous_ctx.system_prompt
    if system_addendum:
        system_prompt = f"{system_prompt}\n\n{system_addendum}" if system_prompt else system_addendum
    memory_used = "semantic_memories" in continuous_ctx.context_sections
    # Read before this turn is stored, so history ends at the previous turn.
    continuous_messages = get_recent_messages_for_continuous(
        conversation_manager=conversation_manager,
        conversation_id=conversation_id,
        limit=12,
    )
    print(f"[ChatTurn] Context: ~{continuous_ctx.token_estimate} tokens, "
          f"semantic={memory_used}, messages={len(continuous_messages)}")

    await emit({
        "type": "thinking",
        "status": "Processing...",
        "memories": {
            "summaries_count": 0, "details_count": 0, "project_docs_count": 0,
            "user_context_count": 0, "wiki_pages_count": 0,
            "cross_session_insights_count": 0, "pattern_count": 0,
            "thread_count": 0, "question_count": 0, "tool_count": 0,
            "has_context": False,
            "context_sizes": {"continuous": len(system_prompt) if system_prompt else 0},
        },
    })
    provider_label = _PROVIDER_LABELS.get(response_provider, response_provider)
    await emit({"type": "thinking", "status": f"Generating response ({provider_label})..."})

    # 2. Model call and tool loop. Each turn carries its own ToolChain: the
    # clients are shared singletons, so never rely on their "last" turn.
    agent_client = _state["agent_client"]
    is_anthropic = turn_client is agent_client
    send_kwargs = dict(
        message=model_message if model_message is not None else user_message,
        memory_context="",  # context is in continuous_system_prompt
        project_id=project_id,
        unsummarized_count=0,
        conversation_id=conversation_id,
        continuous_system_prompt=system_prompt,
        continuous_messages=continuous_messages,
    )
    if extra_send_kwargs:
        send_kwargs.update(extra_send_kwargs)
    if is_anthropic:
        send_kwargs.update(image=image, image_media_type=image_media_type, memory=memory)

    response = await turn_client.send_message(**send_kwargs)
    raw_response = response.raw
    clean_text = response.text
    animations = list(response.gestures or [])
    tool_uses = response.tool_uses
    total_input = response.input_tokens
    total_output = response.output_tokens
    total_cache_read = getattr(response, "cache_read_tokens", 0) or 0
    turn_chain = response.chain
    loop_label = {"local": "Ollama Tool Loop", "openai": "OpenAI Tool Loop"}.get(
        response_provider, "Tool Loop")

    cap = max_tool_iterations()
    if tool_cap is not None:
        cap = min(cap, tool_cap)
    tool_iterations = 0
    tool_names_used: List[str] = []
    generated_images: List[Dict] = []
    hit_tool_cap = False
    while response.stop_reason == "tool_use" and tool_uses:
        if tool_iterations >= cap:
            hit_tool_cap = True
            print(f"[ChatTurn] Tool loop hit the cap ({cap}); ending turn")
            await emit({"type": "debug",
                        "message": f"[{loop_label}] stopped after {cap} iterations (CHAT_MAX_TOOL_ITERATIONS)"})
            break
        tool_iterations += 1
        tool_names = [t["tool"] for t in tool_uses]
        tool_names_used.extend(tool_names)
        await emit({"type": "debug",
                    "message": f"[{loop_label} #{tool_iterations}] stop_reason={response.stop_reason}, tools={tool_names}"})
        await emit({"type": "thinking", "status": f"Executing: {', '.join(tool_names)}..."})

        user_name = None
        if user_id and user_manager:
            profile = user_manager.load_profile(user_id)
            user_name = profile.display_name if profile else None
        tool_ctx = _state["create_tool_context"](
            user_id=user_id,
            user_name=user_name,
            conversation_id=conversation_id,
            project_id=project_id,
        )
        results = await execute_tools_safely(
            _state["execute_tool_batch"], tool_uses, tool_ctx, _state["tool_executors"])
        generated_images.extend(extract_generated_images(tool_uses, results))

        await emit({"type": "debug", "message": f"[Submitting {len(results)} tool results to the model...]"})
        await emit({"type": "thinking", "status": f"Generating response ({provider_label})..."})
        response = await turn_client.continue_with_tool_results(results, chain=turn_chain)
        turn_chain = response.chain or turn_chain
        await emit({"type": "debug",
                    "message": f"[Continuation] stop_reason={response.stop_reason}, "
                               f"has_text={bool(response.text)}, new_tools={len(response.tool_uses)}"})
        await emit({"type": "debug",
                    "message": f"[Continuation text] {response.text[:200] if response.text else '(empty)'}"})

        if is_anthropic:
            # Keep every step's raw text (tags can come before a tool call)
            # but only the final clean text: intermediate "let me check..."
            # text wastes tokens when stored and loaded as context.
            raw_response += "\n" + response.raw
            if response.text:
                clean_text = response.text
            animations.extend(response.gestures or [])
        else:
            # OpenAI/Ollama: the last step replaces (unchanged behavior)
            raw_response = response.raw
            clean_text = response.text
            animations = list(response.gestures or [])
        tool_uses = response.tool_uses
        total_input += response.input_tokens
        total_output += response.output_tokens
        total_cache_read += getattr(response, "cache_read_tokens", 0) or 0

    # 3. Persist: tags, marks, memory, SQLite, tokens, title, summary.
    turn = await finalize_chat_turn(
        user_message=user_message,
        raw_response=raw_response,
        clean_text=clean_text,
        animations=animations,
        conversation_id=conversation_id,
        user_id=user_id,
        input_tokens=total_input,
        output_tokens=total_output,
        cache_read_tokens=total_cache_read,
        provider=response_provider,
        model=response_model,
        tool_iterations=tool_iterations,
        summarize_requested="<memory:summarize>" in raw_response,
        memory_metadata=memory_metadata,
        generate_title=generate_title,
        websocket=websocket,
    )

    # 4. Behavioral sample for cross-context consistency analysis.
    _record_cross_context_sample(turn["clean_text"], user_message, tool_names_used, conversation_id)

    extracted = {k: v for k, v in turn.items() if k not in ("clean_text", "marks")}
    return ChatTurnResult(
        clean_text=turn["clean_text"],
        raw_response=raw_response,
        animations=animations,
        tool_uses=tool_uses or [],
        conversation_id=conversation_id,
        input_tokens=total_input,
        output_tokens=total_output,
        cache_read_tokens=total_cache_read,
        provider=response_provider,
        model=response_model,
        tool_iterations=tool_iterations,
        generated_images=generated_images,
        memory_used=memory_used,
        hit_tool_cap=hit_tool_cap,
        marks=turn["marks"],
        extracted=extracted,
    )
