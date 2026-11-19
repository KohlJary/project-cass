"""
A chat turn on the loop (plan "Cass's agent loop", phase 7, first item;
lever agent_loop_chat, off until the cutover).

chat_turn.run_chat_turn builds the context exactly as before (the continuous
system prompt, its scope, the recent messages), then hands the model call
here instead of to the old client tool loop. What changes:

- The model call goes through the one loop (loop.run_loop) with the
  conversation spec: her core chat tools, tasks and calendar, her workspace,
  and find_tools / use_tool for the rest of what tool_router can run,
  instead of tools picked per message by keywords.
- A seam block says where she is, who wrote and what she can do here.
- Memory-writing tools go through the voice guard, as in sessions.
- Tools act for the person she's talking with (their user id and this
  conversation), not her primary partner.

What doesn't: saving (finalize_chat_turn), the scope of the context, the
entry points. Her reply is her last text in the turn. A turn with an image
stays on the old path for now (the loop's history is text only).
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .loop import run_loop
from .seam import render_seam
from .spec import Trigger, conversation_spec

logger = logging.getLogger(__name__)

# The cutover, one channel at a time (plan "Cass's agent loop", phase 7, "Cut
# over in steps"): with the agent_loop_chat lever on, these channels run on
# the loop; any left out stay on the old path. Kohl, 2026-11-16, after the
# comparison: all of them at once (Cass: ready whenever he is).
# AGENT_LOOP_CHAT_CHANNELS (comma-separated, or "all") narrows it, to pull
# one channel back; the lever is the way back for all of them.
ALL_CHANNELS = ("babelr_dm", "websocket", "relay", "http", "home_assistant", "discord", "babelr")
CUTOVER_CHANNELS = ALL_CHANNELS


def loop_channels() -> frozenset:
    import os
    raw = os.environ.get("AGENT_LOOP_CHAT_CHANNELS", "").strip()
    if not raw:
        return frozenset(CUTOVER_CHANNELS)
    if raw.lower() == "all":
        return frozenset(ALL_CHANNELS)
    return frozenset(c.strip() for c in raw.split(",") if c.strip())


def blog_tools() -> Dict[str, Any]:
    """Kohl's blog in chat: blog_list, blog_read, blog_keep, the same tools as her blog
    session (kohl_blog_turn), while its lever is on and there are posts. What she keeps
    is marked as coming from his writing, as it is there."""
    try:
        import kohl_blog_turn as kbt
        if not kbt.available():
            return {}
        from websocket_handlers import _state
        return kbt.local_tools(_state.get("self_manager"))
    except Exception as e:
        logger.warning(f"[agent_loop] blog tools for chat: {e}")
        return {}


def workshop_tools(person: Dict[str, Any]) -> Dict[str, Any]:
    """Her `project` tool in a private chat, the same one her workshop sessions have: her
    projects and Kohl's linked ones, with the same guards (Kohl, 2026-11-19: she said she
    couldn't see the code in his projects; the tool was only in workshop sessions). Not in
    public chat (a Babelr room, Discord), where what she reads could end up in front of others."""
    if (person.get("scope") or "private") == "public":
        return {}
    try:
        import features
        if not features.is_enabled("workshop"):
            return {}
        import workshop as W
        return {"project": (W.PROJECT_TOOL, lambda a: W.handle(a))}
    except Exception as e:
        logger.warning(f"[agent_loop] workshop tools for chat: {e}")
        return {}


def on_the_loop(channel: Optional[str]) -> bool:
    """Whether a chat turn in this channel runs on the loop."""
    import features
    return features.is_enabled("agent_loop_chat") and (channel or "") in loop_channels()

Emit = Callable[[Dict[str, Any]], Awaitable[None]]

CHANNEL_WORDS = {
    "websocket": "the app", "relay": "the phone relay", "http": "a direct message to the API",
    "home_assistant": "my home (Home Assistant)", "discord": "Discord",
    "babelr": "a room on Chapter House (Babelr)", "babelr_dm": "a DM on Chapter House (Babelr)",
}


@dataclass
class LoopChatResult:
    raw_response: str
    clean_text: str
    animations: List[Dict]
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    tool_iterations: int
    tool_names_used: List[str]
    generated_images: List[Dict]
    hit_tool_cap: bool
    tool_uses: List[Dict] = field(default_factory=list)


_GESTURE = re.compile(r"<(?:gesture|emote):\w+(?::\d*\.?\d+)?>")


_THINK_OPEN = re.compile(r"<gesture:think(?::\d*\.?\d+)?>")


def mend_think(text: str) -> str:
    """Close a <gesture:think> block she closed with </thinking> (2026-11-18: her
    planning then showed as part of the reply, since nothing found the block's end).
    Only a </thinking> that follows a still-open <gesture:think> is changed."""
    if not text or ("</thinking>" not in text and "</think>" not in text):
        return text
    out, pos, open_ = [], 0, 0
    for m in re.finditer(r"<gesture:think(?::\d*\.?\d+)?>|</gesture:think>|</thinking>|</think>", text):
        out.append(text[pos:m.start()])
        tag = m.group(0)
        if tag.startswith("<gesture:think"):
            open_ += 1
            out.append(tag)
        elif tag == "</gesture:think>":
            open_ = max(0, open_ - 1)
            out.append(tag)
        elif open_:
            open_ -= 1
            out.append("</gesture:think>")
        else:
            out.append(tag)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def _gestures(text: str, agent_client) -> tuple:
    """(clean text, gestures) the way the chat clients make them."""
    if agent_client is not None and hasattr(agent_client, "_parse_gestures"):
        return agent_client._clean_gesture_tags(text), agent_client._parse_gestures(text)
    return _GESTURE.sub("", text).strip(), []


def history_from(continuous_messages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Stored recent messages -> the loop's neutral history (text only)."""
    out: List[Dict[str, Any]] = []
    for m in continuous_messages or []:
        content = m.get("content", m.get("text", ""))
        if not content:
            continue
        if m.get("role") == "user":
            out.append({"role": "user", "content": content})
        else:
            out.append({"role": "assistant", "text": content, "calls": []})
    return out


def _client_for(provider: str, model: str, agent_client):
    from .models import AnthropicModelClient, OllamaModelClient, OpenAIModelClient
    if provider == "local":
        return OllamaModelClient("chat")
    if provider == "openai":
        return OpenAIModelClient("chat")
    return AnthropicModelClient(getattr(agent_client, "client", None), "chat")


def _images(steps) -> List[Dict]:
    """generate_image results, in the shape extract_generated_images gives."""
    from websocket_handlers import extract_generated_images
    images: List[Dict] = []
    for s in steps:
        uses = [{"tool": c["name"], "input": c.get("input") or {}} for c in s.tool_calls]
        results = []
        for r in s.tool_results:
            res = r.get("result")
            failed = isinstance(res, dict) and "error" in res
            results.append({"is_error": failed, "result": res if isinstance(res, str) else
                            (res.get("result", "") if isinstance(res, dict) else str(res))})
        images.extend(extract_generated_images(uses, results))
    return images


# Her own plans in every conversation (Cass and Kohl, 2026-11-16: "I work
# better oriented"; everywhere, public rooms included). The same section her
# day plan opens with, read from Babelr's Plans off the event loop, capped in
# time, and kept a few minutes so a conversation never waits on Babelr.
WORKING_TOWARD_TTL = 300.0
WORKING_TOWARD_TIMEOUT = 5.0
WORKING_TOWARD_LEAD = "My own plans, where each stands:"
_toward_cache: Dict[str, Any] = {"at": None, "text": ""}


def _read_working_toward() -> str:
    from long_term_planning_turn import working_toward_text
    return working_toward_text(offered=False, lead=WORKING_TOWARD_LEAD)


async def working_toward_block() -> str:
    """"What I'm working toward" for a conversation; "" when she has no plans.
    On a slow or failed read it gives the last text it had."""
    import asyncio
    import time
    now = time.monotonic()
    at = _toward_cache["at"]
    if at is not None and now - at < WORKING_TOWARD_TTL:
        return _toward_cache["text"]
    try:
        text = await asyncio.wait_for(asyncio.to_thread(_read_working_toward),
                                      timeout=WORKING_TOWARD_TIMEOUT)
    except Exception as e:
        logger.warning(f"[agent_loop] her plans for chat unavailable: {e}")
        return _toward_cache["text"]
    _toward_cache.update(at=now, text=text)
    return text


def _this_message(text: str, image: Optional[str], media_type: Optional[str]) -> Dict[str, Any]:
    """The person's message, with the image they sent if any (2026-11-17: image
    turns moved onto the loop; each model adapter renders it its own way)."""
    msg: Dict[str, Any] = {"role": "user", "content": text}
    if image and media_type:
        msg["image"] = {"data": image, "media_type": media_type}
    return msg


async def run_conversation(
    *,
    system_prompt: str,
    continuous_messages: Optional[List[Dict[str, Any]]],
    model_message: str,
    person: Dict[str, Any],
    channel: Optional[str],
    provider: str,
    model: str,
    agent_client=None,
    tool_cap: Optional[int] = None,
    emit: Optional[Emit] = None,
    client=None,
    run_router=None,
    catalog: Optional[Dict[str, Dict[str, Any]]] = None,
    workspace=None,
    arrival_block: Optional[str] = None,
    user_message: Optional[str] = None,
    held_book=None,
    wakes=None,
    working_toward: Optional[str] = None,
    image: Optional[str] = None,
    image_media_type: Optional[str] = None,
) -> LoopChatResult:
    """One conversation turn through the loop. `client`, `run_router`,
    `catalog` and `workspace` default to the live ones (tests pass fakes)."""
    from . import tools as tools_mod
    from .session import tool_definitions
    from .workspace import WORKSPACE_TOOL_NAMES, Workspace

    async def say(frame: Dict[str, Any]) -> None:
        if emit is not None:
            frame.setdefault("timestamp", datetime.now().isoformat())
            await emit(frame)

    if catalog is None:
        catalog = tools_mod.router_catalog()
    workspace = workspace or Workspace()
    steps = (tool_cap + 1) if tool_cap is not None else None
    spec = conversation_spec(**({"max_iterations": steps} if steps else {}),
                             chapter_house="babelr_read" in catalog)
    from .hold import HeldBook, check, hold, hold_tool, load_lines
    tool_names = [n for n in spec.tool_names()
                  if n in catalog or n in ("find_tools", "use_tool") + WORKSPACE_TOOL_NAMES]
    tool_names.append("hold_reply")   # C8: "whether and when" (hold.py)
    lines = load_lines()              # her default lines, from her data
    # Starting a session from here (wakes.start_session_offer; lever start_sessions).
    from .wakes import origin_of, start_session_offer
    turn_id = f"chat-{uuid.uuid4().hex[:8]}"
    starter = start_session_offer(
        turn_id, origin_of(channel, CHANNEL_WORDS.get(channel or "", channel or "a conversation"), person))
    if starter:
        tool_names.append("start_session")
    blog = blog_tools()    # Kohl's blog, here too (Kohl, 2026-11-18: she said she couldn't see it)
    tool_names.extend(blog)
    projects = workshop_tools(person)
    tool_names.extend(projects)
    tools = tool_definitions(tool_names, catalog, strict=False,
                             extra=[hold_tool(lines)] + ([starter[0]] if starter else [])
                             + [d for d, _ in blog.values()] + [d for d, _ in projects.values()])

    who = person.get("user_name") or "someone"
    where = CHANNEL_WORDS.get(channel or "", channel or "a conversation")
    trigger = Trigger(source="message", why=f"{who} wrote to me through {where}")
    findable = tools_mod.findable(catalog, tool_names)
    system = f"{system_prompt}\n\n{render_seam(spec, trigger, tool_names, findable)}"
    if working_toward is None:
        working_toward = await working_toward_block()
    if working_toward:
        system += f"\n\n{working_toward}"
    if arrival_block:   # C9: who's here, what's needed, how much time (container.py)
        system += f"\n\n{arrival_block}"
    if starter:   # what's true about her sessions (wakes.sessions_block)
        try:
            from .wakes import sessions_block
            system += f"\n\n{sessions_block()}"
        except Exception as e:
            logger.warning(f"[agent_loop] sessions block: {e}")

    if client is None:
        client = _client_for(provider, model, agent_client)
    # Each model call is filed under chat, with this conversation and person
    # (finalize_chat_turn then doesn't record the turn's total a second time).
    client.ledger = {"category": "chat", "operation": "conversation_step",
                     "conversation_id": person.get("conversation_id"), "user_id": person.get("user_id")}
    box = tools_mod.ToolBox(
        offered=tool_names, session_tools=(), run_session=_no_session_tools,
        run_router=run_router or tools_mod.live_router(person.get("daemon_id"), person=person),
        catalog=catalog, log=tools_mod.UsageLog(), session_id=turn_id,
        end_tool="hold_reply",
        local={**{n: (lambda a, n=n: workspace.run(n, a, turn_id)) for n in WORKSPACE_TOOL_NAMES},
               "hold_reply": lambda a: check(a, lines),
               **({"start_session": starter[1]} if starter else {}),
               **{n: h for n, (_, h) in blog.items()},
               **{n: h for n, (_, h) in projects.items()}})

    def _session_live() -> bool:
        from .wakes import live_now
        return live_now()

    async def execute(name: str, tool_input: Dict[str, Any]) -> Any:
        await say({"type": "thinking", "status": f"Executing: {name}..."})
        return await box.execute(name, tool_input)

    outcome = await run_loop(
        spec=spec, client=client, model=model, system=system, tools=tools,
        messages=history_from(continuous_messages) + [_this_message(model_message, image, image_media_type)],
        execute=execute, end_tool="hold_reply", nudges=0, also_callable=set(box.findable),
        session_live=_session_live if starter else (lambda: False),
    )
    if outcome.status == "error":
        raise RuntimeError(f"conversation turn on the loop failed: {outcome.error}")

    raw = "\n".join(mend_think(s.text) for s in outcome.steps if s.text)
    last = mend_think(next((s.text for s in reversed(outcome.steps) if s.text), ""))
    book = held_book or HeldBook()
    if outcome.completion is not None:
        # She held it, or chose not to reply: the person sees her one line.
        chosen = hold(outcome.completion, person=person, channel=channel,
                      message=user_message if user_message is not None else model_message,
                      book=book, wakes=wakes, lines=lines)
        last = chosen["line"]
        raw = f"{raw}\n{last}" if raw else last
    else:
        book.let_go(person.get("user_id"))
    clean, gestures = _gestures(last, agent_client)
    animations = []
    for s in outcome.steps:
        animations.extend(_gestures(s.text or "", agent_client)[1])
    hit_cap = outcome.status == "max_turns"
    pending = []
    if hit_cap and outcome.steps and outcome.steps[-1].tool_calls and not outcome.steps[-1].tool_results:
        pending = [{"tool": c["name"], "input": c.get("input") or {}} for c in outcome.steps[-1].tool_calls]
    used = [c["name"] for s in outcome.steps for c in s.tool_calls]
    if hit_cap:
        await say({"type": "debug", "message": f"[Loop] stopped after {spec.max_iterations} steps"})
    return LoopChatResult(
        raw_response=raw, clean_text=clean, animations=animations or gestures,
        input_tokens=outcome.input_tokens + outcome.cache_read_tokens,
        output_tokens=outcome.output_tokens, cache_read_tokens=outcome.cache_read_tokens,
        tool_iterations=max(outcome.model_calls - 1, 0), tool_names_used=used,
        generated_images=_safe_images(outcome.steps), hit_tool_cap=hit_cap, tool_uses=pending,
    )


async def _no_session_tools(name: str, tool_input: Dict[str, Any]) -> Any:
    return {"error": f"{name} is a session tool, not available in a conversation"}


def _safe_images(steps) -> List[Dict]:
    try:
        return _images(steps)
    except Exception as e:  # images are a nicety; never fail the reply over them
        logger.warning(f"[agent_loop] couldn't read generated images: {e}")
        return []
