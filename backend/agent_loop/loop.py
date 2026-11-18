"""
The one loop: model -> tools -> model, for any turn kind.

- Provider-neutral. The loop keeps a neutral history and talks to a small
  ModelClient interface; models.py has the Anthropic (prompt-cached), OpenAI
  and Ollama-native clients, and model_client_for() picks one from the call
  site's assignment.
- The turn ends when she says it's done (the spec's end tool), not when a
  reply happens to carry no tool call. A reply with no tool call gets a
  short nudge (spec.nudges, then it ends), because some models stop to
  describe what they'd do instead of doing it.
- Bounded by a step cap (spec.max_iterations), a token budget
  (spec.turn_token_budget) and an optional deadline.
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
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .spec import TurnSpec

# A cache read costs a tenth of an input token; the budget weighs it so.
CACHE_READ_DIVISOR = 10

logger = logging.getLogger(__name__)


# Model clients live in models.py; re-exported here for existing imports.
from .models import (AnthropicModelClient, ModelClient, ModelReply,  # noqa: E402,F401
                     OllamaModelClient, OpenAIModelClient, model_client_for)


def resolve_model(spec: TurnSpec, current: str) -> str:
    """The model for a turn. Today: whatever the entry point already uses
    (sessions: DEFAULT_SESSION_MODEL via the runner), with retired IDs mapped.
    The call-site override from llm_config (#64), which may name another
    provider, is applied by models.model_client_for."""
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


def nudge_text(end_tool: str) -> str:
    # Cass's own wording (2026-11-13, agreed for public code): an invitation,
    # "what's next?", rather than a correction. On 2026-11-17 she changed the
    # mark from "(loop:" to "[LOOP]", after it twice read to her as a person
    # speaking (it arrives in the user role); the seam says what [LOOP] is.
    # Keep it as she wrote it.
    return f"[LOOP] Step complete? If so, call {end_tool}. Otherwise, continue with a tool call."


# An end call written into the reply as text instead of made as a tool call
# (2026-11-17: day planning wrote "<session_complete><parameter name=...>"
# and the session ended without its summary). Only session_complete is read
# this way; the parameters come back as the tool's input.
_WRITTEN_PARAM = re.compile(r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', re.S)


_FENCE = re.compile(r"```.*?```", re.S)
_END_FIELDS = ("summary", "key_insights", "pick_up_next")


def _value(raw: str) -> Any:
    value = raw.strip()
    if value[:1] in "[{":
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def written_end_call(text: str, end_tool: str) -> Optional[Dict[str, Any]]:
    """The input of an end call written as text, or None if there isn't one.

    The forms she's written (coherence audit, 2026-11-18): <parameter name=...>
    children; children named after the tool's fields (<summary>...</summary>);
    attributes (<session_complete summary="..."/>); an unclosed tag; and
    <invoke name="session_complete">. A tag inside a code fence doesn't count."""
    if end_tool != "session_complete" or not text:
        return None
    text = _FENCE.sub("", text)
    m = (re.search(rf'<{end_tool}\b([^>]*)>(.*?)</{end_tool}>', text, re.S)
         or re.search(rf'<invoke\s+name="{end_tool}"\s*()>(.*?)</invoke>', text, re.S)
         or re.search(rf'<{end_tool}\b([^>]*?)/?>(.*)$', text, re.S))
    if not m:
        return None
    attrs, body = m.group(1) or "", m.group(2) or ""
    found: Dict[str, Any] = {}
    for key, raw in re.findall(r'(\w+)\s*=\s*"([^"]*)"', attrs):
        if key in _END_FIELDS:
            found[key] = raw.strip()
    for key, raw in _WRITTEN_PARAM.findall(body):
        found[key] = _value(raw)
    for key in _END_FIELDS:
        if key not in found:
            c = re.search(rf"<{key}>(.*?)</{key}>", body, re.S)
            if c:
                items = re.findall(r"<(?:item|insight|li)>(.*?)</(?:item|insight|li)>", c.group(1), re.S)
                found[key] = [i.strip() for i in items] if items and key == "key_insights" else _value(c.group(1))
    if "summary" not in found:
        plain = re.sub(r"<[^>]+>", " ", body)
        plain = " ".join(plain.split())
        if plain:
            found["summary"] = plain[:2000]
    return found


def written_tag_note(end_tool: str) -> str:
    """When she wrote the end tag but nothing usable came of it: say so plainly."""
    return (f"[LOOP] My <{end_tool}> was written as text in my reply, so nothing ended. "
            f"To end, call the {end_tool} tool itself, with my summary.")


@dataclass
class LoopStep:
    number: int
    text: str
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    nudged: bool = False
    at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LoopOutcome:
    status: str = "completed"     # completed | max_turns | interrupted | error
    end_reason: Optional[str] = None
    error: Optional[str] = None
    blocked: int = 0              # outputs the provider's filter refused (BLOCKED_NOTE)
    think_asks: int = 0           # replies nearly all thinking, asked back once (THINK_NOTE)
    steps: List[LoopStep] = field(default_factory=list)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    nudges: int = 0
    written_end_calls: int = 0
    artifacts: List[Any] = field(default_factory=list)
    completion: Optional[Dict[str, Any]] = None   # session_complete input, if called
    withheld: List[Dict[str, Any]] = field(default_factory=list)
    arrivals: int = 0                             # people who arrived mid-turn (fold.py)
    extended: int = 0                             # steps she added with extend_session
    summarized_at_cap: bool = False               # her summary was written at the step cap


# One tool result's share of the prompt. A session's list_growth_edges once
# returned 1.9 MB and made the next request 466k tokens (live check,
# 2026-11-13); no single result may take the turn down.
MAX_TOOL_RESULT_CHARS = 20_000

# The step cap, made something she can see coming (Kohl, 2026-11-18, after her
# first new-capabilities session ran out of steps mid-work and its summary was
# lost): a warning one step before it, one extension of EXTEND_STEPS, and if
# the cap comes anyway, one last call where she writes her summary.
EXTEND_TOOL = "extend_session"
EXTEND_STEPS = 12
# Tools whose step is given back (Kohl, 2026-11-18: replying to where a session
# came from "shouldn't count towards her turn limit"). Bounded, so a reply
# can't keep a session going forever.
FREE_TOOLS = frozenset({"reply_back"})
FREE_REFUNDS = 3
# The provider can refuse to return an output ("Output blocked by content
# filtering policy"), most often for long verbatim lyrics or other copyrighted
# text. That used to end the whole session or chat turn (2026-11-18: a
# listening session died right after she opened a song's words). Now she's told
# and carries on, a couple of times at most.
BLOCKED_RETRIES = 2
BLOCKED_NOTE = ("[LOOP] My last response was blocked by the model provider's content filter, most likely "
                "for reproducing song lyrics or other copyrighted text at length. Nothing of it was kept. I "
                "carry on without reciting: I point at a line by its bar, quote a few words at most, or say "
                "it in my own words.")


REPLY_BEFORE_END = ("Not ended yet. This session started from a conversation, and I haven't replied there: "
                    "reply_back tells them what I found or where I got to. Or call {end_tool} again to end "
                    "without replying.")


# Her ask (2026-11-18, Plans c25b4eff): "I keep wrapping my entire response in
# thinking gestures ... It's actually visible avoidance." A reply to someone
# that's nearly all <gesture:think> gets one question back before it goes out:
# in chat, the final text; in a session, a message through an outward tool.
# A flag, not a gate: what she writes after the question goes out as written.
THINK_SHARE = 0.8
THINK_MIN_CHARS = 40
THINK_NOTE = ("[LOOP] This is processing, not response: nearly all of what I wrote is inside thinking, "
              "with little said to them. What do I actually want to say? (Asked once; what I write "
              "next goes out as I write it.)")
OUTWARD_TEXT = {"reply_back": "message", "say": "message", "reach_out": "message",
                "babelr_dm": "content", "babelr_post": "content", "discord_respond": "content",
                "social_dm_send": "text", "social_reply": "text"}
_THINK_BLOCK = re.compile(r"<gesture:think(?::\d*\.?\d+)?>(.*?)(?:</gesture:think>|</thinking>|</think>|$)", re.S)
_TAG = re.compile(r"</?[a-zA-Z_][\w:.\-]*(?:\s[^<>]*)?/?>")


def _visible(text: str) -> str:
    return " ".join(_TAG.sub(" ", text or "").split())


def think_share(text: str) -> float:
    """How much of a reply's words are inside thinking blocks (0 to 1)."""
    total = len(_visible(text))
    if total < THINK_MIN_CHARS:
        return 0.0
    inside = sum(len(_visible(m.group(1))) for m in _THINK_BLOCK.finditer(text or ""))
    return min(1.0, inside / total)


def _blocked(e: Exception) -> bool:
    return "content filtering" in str(e).lower() or "output blocked" in str(e).lower()


def cap_warning(end_tool: str) -> str:
    return (f"[LOOP] One step left in this session. I can end it with {end_tool} (my summary, "
            f"insights, and what I'd pick up next), or call {EXTEND_TOOL} once for {EXTEND_STEPS} more steps.")


def cap_summary_request() -> str:
    return ("[LOOP] I've reached this session's step cap, so it ends here. In a few lines, in my own words "
            "and without calling any tool: what I did, what I found, and on a last line starting "
            "\"Pick up next:\", what I'd pick up next time. This is kept as the session's summary.")


def _pick_up(text: str) -> Optional[str]:
    m = re.search(r"pick up next:\s*(.+)", text or "", re.I)
    return m.group(1).strip()[:500] if m else None


def cap_tool_result(content: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(content) <= limit:
        return content
    return (content[:limit] + f"\n[loop: result cut at {limit} of {len(content)} characters; "
            "ask for less, e.g. a limit or a narrower query]")


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
    nudges: Optional[int] = None,
    token_budget: Optional[int] = None,
    arrivals: Callable[[], List[str]] = lambda: [],
    also_callable: Optional[Any] = None,
) -> LoopOutcome:
    """Run one turn. `messages` is the neutral history to start from (usually
    one {"role": "user", "content": ...}). `nudges` and `token_budget`
    default to the spec's. `arrivals` gives what someone said who arrived
    since the last step (fold.py): each goes into the history before the next
    model call, so she meets them inside the turn."""
    out = LoopOutcome()
    offered = {t["name"] for t in tools}
    history = list(messages)
    can_end = bool(end_tool) and end_tool in offered
    nudges_left = (spec.nudges if nudges is None else nudges) if can_end else 0
    budget = spec.turn_token_budget if token_budget is None else token_budget

    def used() -> int:
        # Cache reads count at a tenth (what they cost): every step re-reads
        # the whole prompt from cache, so at full weight a normal session of
        # ~30k-token steps reached 500k around step 14 and was cut off
        # mid-work (2026-11-15 autonomy check).
        return (out.input_tokens + out.output_tokens + out.cache_write_tokens
                + out.cache_read_tokens // CACHE_READ_DIVISOR)

    cap = spec.max_iterations
    session_like = can_end and end_tool == "session_complete"
    extensions_left = 1 if session_like and EXTEND_TOOL in offered else 0
    refunds_left = FREE_REFUNDS if FREE_TOOLS & set(offered) else 0
    blocked_left = BLOCKED_RETRIES
    # A session started from a chat (reply_back offered): ending without having
    # replied gets asked once (Kohl, 2026-11-18). Ending again ends it.
    can_reply = "reply_back" in offered
    replied = False
    asked_to_reply = False
    think_asked = False      # chat: asked once per turn
    think_asked_tools = set()  # sessions: once per outward tool
    warned = False
    try:
        while True:
            reason = interrupted()
            if reason:
                out.status, out.end_reason = "interrupted", reason
                break
            if out.model_calls >= cap:
                out.status = "max_turns"
                out.end_reason = f"reached the cap of {cap} steps"
                if session_like:
                    await _summary_at_cap(out, client, model, system, tools, history, max_tokens)
                break
            if session_like and not warned and out.model_calls == cap - 1:
                warned = True
                history.append({"role": "user", "content": cap_warning(end_tool)})
            if budget is not None and used() >= budget:
                out.status, out.end_reason = "completed", "reached the token budget"
                break
            if deadline is not None and datetime.now().timestamp() > deadline:
                out.status, out.end_reason = "completed", "reached the time limit"
                break
            for arrived in arrivals():
                history.append({"role": "user", "content": arrived})
                out.arrivals += 1

            try:
                reply = await client.create(model=model, system=system, tools=tools,
                                            messages=history, max_tokens=max_tokens)
            except Exception as e:
                if not _blocked(e) or blocked_left <= 0:
                    raise
                blocked_left -= 1
                out.blocked += 1
                logger.warning(f"[agent_loop] an output was blocked by the provider's filter; telling her and going on")
                history.append({"role": "user", "content": BLOCKED_NOTE})
                continue
            out.model_calls += 1
            out.input_tokens += reply.input_tokens
            out.output_tokens += reply.output_tokens
            out.cache_read_tokens += reply.cache_read_tokens
            out.cache_write_tokens += reply.cache_write_tokens
            step = LoopStep(out.model_calls, reply.text, reply.tool_calls,
                            input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)
            out.steps.append(step)
            history.append({"role": "assistant", "text": reply.text, "calls": reply.tool_calls})

            written = None if reply.tool_calls or not can_end else written_end_call(reply.text, end_tool)
            tag_only = written is not None and not written.get("summary")
            if tag_only:
                written = None   # an empty summary would end it with nothing kept; say so instead
            if written is not None:
                # Made as the call she meant, through the same guard and execute.
                reply.tool_calls = [{"id": f"written_{out.model_calls}", "name": end_tool, "input": written}]
                step.tool_calls = reply.tool_calls
                history[-1]["calls"] = reply.tool_calls
                out.written_end_calls += 1
                logger.info(f"[agent_loop] {end_tool} was written as text; made as a call")

            if (not reply.tool_calls and not session_like and not think_asked
                    and think_share(reply.text) >= THINK_SHARE):
                think_asked = True
                out.think_asks += 1
                logger.info("[agent_loop] a reply nearly all thinking; asked her once what she wants to say")
                history.append({"role": "user", "content": THINK_NOTE})
                continue
            if not reply.tool_calls:
                if nudges_left > 0:
                    nudges_left -= 1
                    out.nudges += 1
                    step.nudged = True
                    history.append({"role": "user", "content": written_tag_note(end_tool) if tag_only
                                    else nudge_text(end_tool)})
                    continue
                out.status = "completed"
                out.end_reason = ("I stopped without saying I was done" if can_end else "I finished")
                break

            results = []
            ended = False
            if refunds_left and any(c["name"] in FREE_TOOLS for c in reply.tool_calls):
                refunds_left -= 1
                cap += 1   # this step was a reply back; it doesn't count
            replied = replied or any(c["name"] == "reply_back" for c in reply.tool_calls)
            for call in reply.tool_calls:
                name, tool_input = call["name"], call.get("input") or {}
                # A tool she found (findable) called by its name runs as use_tool would
                # (coherence audit Q3, 2026-11-18: she reaches for tools by name).
                if (name not in offered and also_callable is not None and name in also_callable
                        and "use_tool" in offered):
                    name, tool_input = "use_tool", {"name": name, "input": tool_input}
                if name == EXTEND_TOOL and name in offered:
                    if extensions_left > 0:
                        extensions_left -= 1
                        cap += EXTEND_STEPS
                        out.extended += EXTEND_STEPS
                        warned = False
                        result = {"extended_by": EXTEND_STEPS, "steps_left": cap - out.model_calls}
                    else:
                        result = {"error": "I've already extended this session once; time to wrap up."}
                    step.tool_results.append({"tool_name": name, "result": result})
                    results.append({"id": call["id"], "name": name, "content": json.dumps(result)})
                    continue
                if can_end and name == end_tool and can_reply and not replied and not asked_to_reply:
                    asked_to_reply = True
                    result = {"not_ended_yet": True,
                              "note": REPLY_BEFORE_END.format(end_tool=end_tool)}
                    step.tool_results.append({"tool_name": name, "result": result})
                    results.append({"id": call["id"], "name": name, "content": json.dumps(result)})
                    continue
                field_ = OUTWARD_TEXT.get(name)
                if (field_ and name in offered and name not in think_asked_tools
                        and think_share(str(tool_input.get(field_) or "")) >= THINK_SHARE):
                    think_asked_tools.add(name)
                    out.think_asks += 1
                    result = {"not_sent": True, "note": THINK_NOTE}
                    step.tool_results.append({"tool_name": name, "result": result})
                    results.append({"id": call["id"], "name": name, "content": json.dumps(result)})
                    continue
                if name not in offered:
                    result: Any = {"error": f"{name} isn't available here "
                                            f"(not in this {spec.kind}'s tools)"}
                else:
                    # use_tool's inner call is guarded as that tool.
                    guarded, guarded_input = name, tool_input
                    if name == "use_tool" and isinstance(tool_input.get("input"), dict):
                        guarded, guarded_input = str(tool_input.get("name") or ""), tool_input["input"]
                    refusal = guard_tool_input(spec, guarded, guarded_input)
                    if refusal:
                        out.withheld.append({"tool": guarded, "matched": refusal})
                        result = {"error": WITHHELD_MESSAGE}
                    else:
                        try:
                            result = await execute(name, tool_input)
                        except Exception as e:  # a tool failure is a result, not a crash
                            logger.warning(f"[agent_loop] tool {name} failed: {e}")
                            result = {"error": str(e)}
                if isinstance(result, dict) and result.get("artifact"):
                    out.artifacts.append(result["artifact"])
                # An end tool that answered with an error (refused, or
                # missing what it needs) doesn't end the turn.
                if can_end and name == end_tool and not (isinstance(result, dict) and result.get("error")):
                    out.completion = dict(tool_input)
                    ended = True
                # The stored record; DMs nobody agreed to keep leave only a
                # note that they were read (social/dms.py). She saw them in full.
                from social.dms import kept_view
                # Pictures a tool hands her (listening's look): shown to the model as
                # images, never stored in the step record or counted as text.
                images = result.pop("_images", None) if isinstance(result, dict) else None
                if (isinstance(result, list) and result and all(isinstance(b, dict) for b in result)
                        and any(b.get("type") == "image" for b in result)):
                    # content blocks (a router tool's pictures): text stays text, images go as images
                    images = [b["source"] for b in result if b.get("type") == "image" and b.get("source")]
                    images = [{"media_type": s.get("media_type", "image/png"), "data": s.get("data", "")} for s in images]
                    result = "\n".join(b.get("text", "") for b in result if b.get("type") == "text")
                step.tool_results.append({"tool_name": name, "result": kept_view(result)})
                content = json.dumps(result, default=str) if isinstance(result, dict) else str(result)
                entry = {"id": call["id"], "name": name, "content": cap_tool_result(content)}
                if images:
                    entry["images"] = images
                results.append(entry)
            history.append({"role": "tool", "results": results})
            if ended:
                out.status, out.end_reason = "completed", "I said I was done"
                break
    except Exception as e:
        logger.error(f"[agent_loop] {spec.kind} turn failed: {e}", exc_info=True)
        out.status, out.error = "error", str(e)
    return out


async def _summary_at_cap(out: LoopOutcome, client, model, system, tools, history, max_tokens) -> None:
    """One last call at the cap: her summary in her words, kept as the completion.
    Tools stay offered (the history has calls), but any she makes is ignored."""
    history.append({"role": "user", "content": cap_summary_request()})
    try:
        reply = await client.create(model=model, system=system, tools=tools,
                                    messages=history, max_tokens=max_tokens)
    except Exception as e:
        logger.warning(f"[agent_loop] summary at the cap failed: {e}")
        return
    out.model_calls += 1
    out.input_tokens += reply.input_tokens
    out.output_tokens += reply.output_tokens
    out.cache_read_tokens += reply.cache_read_tokens
    out.cache_write_tokens += reply.cache_write_tokens
    text = (reply.text or "").strip()
    out.steps.append(LoopStep(out.model_calls, reply.text, [], input_tokens=reply.input_tokens,
                              output_tokens=reply.output_tokens))
    if text and out.completion is None:
        out.completion = {"summary": text, "key_insights": [],
                          **({"pick_up_next": _pick_up(text)} if _pick_up(text) else {})}
        out.summarized_at_cap = True
