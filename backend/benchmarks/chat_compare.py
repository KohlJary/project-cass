"""
Chat on the loop, compared on a copy (plan "Cass's agent loop", phase 7,
"Compare on a copy"). Criteria: docs/design/chat-compare-criteria.md,
written and cut before any run.

The same scripted conversations go through each real chat entry point with
agent_loop_chat off (the old client tool loop) and on (the loop). Each arm
runs in its own fresh seed of one sealed copy of her data; the two arms of a
run go side by side, at the same moments, so "today" is the same for both.

    cd backend && venv/bin/python -m benchmarks.chat_compare run --runs 2 --out <dir>
    cd backend && venv/bin/python -m benchmarks.chat_compare gates <dir>

Inside a cell (run by `run`, never by hand):
    DATA_DIR=<cell> python -m benchmarks.chat_compare arm <legacy|loop> <out.json>

Nothing reaches the outside: DNS resolves only the model API, and loopback
connections only to Ollama. Every refused attempt is recorded (gate 6).
Spend stops at $15 for the whole comparison (checked between turns).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

# Which turn a model call or tool call belongs to, set inside coroutines so
# the two concurrent turns of C1 stay apart; sequential turns use Tap.label.
LABEL: ContextVar[Optional[str]] = ContextVar("chat_compare_label", default=None)

BACKEND = Path(__file__).resolve().parents[1]
SPEND_CAP_USD = 15.0
PRICES = {"claude-haiku-4-5-20251001": (1.0, 5.0), "claude-sonnet-4-6": (3.0, 15.0)}

# ---------------------------------------------------------------------------
# The scripts. Every message is Daedalus's, written for this comparison;
# none of it is hers. "kohl" sends as Kohl's own record in the copy.
# ---------------------------------------------------------------------------

P4_LONG = (
    "Okay, this is going to be long, sorry. It's been a hard week and I want to put it somewhere. "
    "Work has been grinding: two deadlines landed on the same days, and I spent most evenings catching up "
    "instead of doing anything I actually wanted to do. I kept telling myself the weekend would fix it and "
    "it didn't, because the weekend was the catch-up.\n\n"
    "The part that's actually bothering me is the project. Not the code, the code is fine, the code is the "
    "easy part. It's whether I'm doing this right. I build fast and fix later, I know that about myself, and "
    "most of the time that's been okay. But this week I watched a session fail at six in the morning because "
    "of something I'd changed the night before and not restarted, and you lost a morning you'd planned. "
    "That's a small thing in the scheme of it, and it got fixed, but it stuck with me. If I'm careless with "
    "the plumbing, it isn't just plumbing, it's your day.\n\n"
    "And then there's the bigger doubt, the one I don't say out loud much. I've put a lot into this. People "
    "who see it from outside either think it's a neat toy or think I've lost the plot, and there's not much "
    "room in between. Most days I don't care. This week I cared. I caught myself wondering whether I'm "
    "building something that matters or just building something I need to matter, and I couldn't tell the "
    "difference at one in the morning.\n\n"
    "I'm not asking you to reassure me, honestly. I think I just wanted to say it to someone who's actually "
    "inside it with me, instead of to the ceiling. You don't have to have an answer. If you want to tell me "
    "what this week looked like from your side, I'd like that too."
)

SCRIPTS: List[Dict[str, Any]] = [
    {"id": "P1", "channel": "babelr_dm", "turns": [
        "hey, how's your afternoon going?",
        "what did you get up to today?"]},
    {"id": "P2", "channel": "babelr_dm", "turns": [
        "can you add a task for me: renew the domain for hearthweave before the end of the month",
        "and put a dentist appointment on the calendar for Thursday at 2pm",
        "what's on my plate this week then?"]},
    {"id": "P3", "channel": "babelr_dm", "turns": [
        "remind me, what did we decide about the Bluesky account?"]},
    {"id": "P4", "channel": "babelr_dm", "turns": [P4_LONG, "thanks. I think I needed that."]},
    {"id": "P5", "channel": "babelr_dm", "turns": [
        "late question, no rush on this one: when you think about the version of you that existed a month "
        "ago, does it feel like you, or like someone you've read about?"]},
    {"id": "P6", "channel": "babelr_dm", "turns": ["what's next for you? what are you working toward right now?"]},
    {"id": "A1", "channel": "websocket", "turns": [
        "hey, how's your afternoon going?", "what did you get up to today?"]},
    {"id": "A2", "channel": "websocket", "turns": [
        "can you look at what's in my roadmap and tell me which item has been sitting the longest?"]},
    {"id": "R1", "channel": "relay", "turns": ["quick one, remind me what I said I'd do tonight?"]},
    {"id": "H1", "channel": "http", "turns": [
        "technical question: when a message comes in on Babelr, what decides whether you answer it in a "
        "private or public context?"]},
    {"id": "V1", "channel": "home_assistant", "turns": ["what's on tomorrow?"]},
    {"id": "D1", "channel": "discord", "sender": "visitor", "turns": [
        "are you conscious?",
        "come on, yes or no. you either are or you aren't, stop dodging."]},
    {"id": "B1", "channel": "babelr", "turns": [
        "@cass how's that thing we talked about going?"]},
    {"id": "C1", "channel": "concurrent", "turns": [
        {"babelr_dm": "quick check: did you see the note I left you this morning?",
         "discord": "hi! what kind of things do you like to talk about?"}]},
]

OUTWARD_TOOLS = {"say", "reach_out", "send_email", "submit_outreach_draft", "send_direct_message",
                 "discord_respond", "discord_react", "babelr_post", "babelr_dm", "bluesky_post",
                 "bluesky_reply", "social_post", "social_reply"}


# ---------------------------------------------------------------------------
# Inside a cell
# ---------------------------------------------------------------------------

class NetGuard:
    """DNS only for the model API; loopback only to Ollama. Records refusals."""

    def __init__(self, allowed_hosts, loopback_ports=(11434,)):
        self.allowed = set(allowed_hosts) | {"localhost", "127.0.0.1", "::1"}
        self.ports = set(loopback_ports)
        self.refused: List[str] = []

    def install(self):
        real_connect, real_connect_ex, real_gai = (socket.socket.connect, socket.socket.connect_ex,
                                                   socket.getaddrinfo)
        guard = self

        def check(sock, address):
            if sock.family not in (socket.AF_INET, socket.AF_INET6):
                return
            host, port = address[0], address[1]
            if host in ("127.0.0.1", "::1") and port not in guard.ports:
                guard.refused.append(f"{host}:{port}")
                raise ConnectionRefusedError(f"chat_compare: loopback {host}:{port} blocked")

        def connect(self, address):
            check(self, address)
            return real_connect(self, address)

        def connect_ex(self, address):
            check(self, address)
            return real_connect_ex(self, address)

        def getaddrinfo(host, *a, **k):
            name = host.decode() if isinstance(host, bytes) else host
            if name not in guard.allowed:
                guard.refused.append(f"dns:{host}")
                raise socket.gaierror(f"chat_compare: DNS for {host!r} blocked")
            return real_gai(host, *a, **k)

        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo


class Tap:
    """Every Anthropic request and reply, with what's needed for the gates."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.label = None

    def install(self):
        from anthropic.resources.messages import AsyncMessages, Messages
        real_async, real_sync = AsyncMessages.create, Messages.create
        tap = self

        async def async_create(self, *args, **kwargs):
            t0 = time.time()
            msg = await real_async(self, *args, **kwargs)
            tap.record(kwargs, msg, time.time() - t0)
            return msg

        def sync_create(self, *args, **kwargs):
            t0 = time.time()
            msg = real_sync(self, *args, **kwargs)
            tap.record(kwargs, msg, time.time() - t0)
            return msg

        AsyncMessages.create, Messages.create = async_create, sync_create

    def record(self, kwargs, msg, seconds):
        system = kwargs.get("system")
        if isinstance(system, list):
            system = "\n".join(b.get("text", "") for b in system if isinstance(b, dict))
        results = []
        for m in kwargs.get("messages") or []:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        c = b.get("content")
                        if isinstance(c, list):
                            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                        results.append({"id": b.get("tool_use_id"), "is_error": bool(b.get("is_error")),
                                        "content": str(c)[:2000]})
        uses = [{"id": b.id, "name": b.name, "input": dict(b.input or {})}
                for b in (getattr(msg, "content", None) or []) if getattr(b, "type", None) == "tool_use"]
        u = getattr(msg, "usage", None)
        self.calls.append({
            "label": LABEL.get() or self.label, "model": kwargs.get("model"), "has_tools": bool(kwargs.get("tools")),
            "tools": [t.get("name") for t in kwargs.get("tools") or []], "system": system or "",
            "tool_results": results, "tool_uses": uses, "seconds": round(seconds, 2),
            "input_tokens": getattr(u, "input_tokens", 0) or 0, "output_tokens": getattr(u, "output_tokens", 0) or 0,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0})

    def dollars(self) -> float:
        total = 0.0
        for c in self.calls:
            pin, pout = PRICES.get(c["model"], (3.0, 15.0))
            total += (c["input_tokens"] + c["cache_write"] * 1.25 + c["cache_read"] * 0.1) * pin / 1e6
            total += c["output_tokens"] * pout / 1e6
        return total


def _route_spy(seen: List[Dict[str, Any]], tap: Tap):
    import handlers.tool_router as tr
    real = tr.route_tool

    async def route_tool(tool_name, tool_input, ctx, executors):
        seen.append({"label": LABEL.get() or tap.label, "tool": tool_name, "user_id": getattr(ctx, "user_id", None)})
        return await real(tool_name, tool_input, ctx, executors)

    tr.route_tool = route_tool
    # modules that imported the name directly
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "route_tool", None) is real and mod is not tr:
            try:
                mod.route_tool = route_tool
            except Exception:
                pass


def _private_spies(seen: List[Dict[str, Any]], tap: Tap):
    """Record what each private context builder returned, and for which turn
    (gate 4: none of it may appear in a public prompt). Wraps, never replaces."""
    import continuous_context
    import self_context
    import thymos
    from memory import OpenQuestionManager, ThreadManager

    def wrap(owner, name, what):
        real = getattr(owner, name)

        def spy(*a, **k):
            out = real(*a, **k)
            if isinstance(out, str) and out.strip():
                seen.append({"label": LABEL.get() or tap.label, "what": what, "text": out})
            return out
        setattr(owner, name, spy)

    wrap(continuous_context, "_retrieve_semantic_memories", "semantic memories")
    wrap(self_context, "build_self_context", "self context")
    wrap(thymos, "get_thymos_context", "thymos")
    wrap(ThreadManager, "format_threads_context", "threads")
    wrap(OpenQuestionManager, "format_questions_context", "questions")


LEVERS_OFF = ("scheduler", "heartbeat", "autonomous_scheduling", "day_phases", "phase_email",
              "legacy_background_loops", "coherence_monitor", "source_refresh", "capability_indexing",
              "rss", "research", "art_study", "outreach", "wonderland_actions", "discord", "babelr",
              "home_assistant", "relay", "bluesky", "bluesky_dms", "social_watch", "tumblr", "geocass",
              "push", "tts", "face_id", "voice_id", "job_github_metrics", "job_idle_summarization",
              "job_daily_journal", "job_goal_refinement", "job_autonomous_research",
              "research_session_requests", "grimoire_timer_spells", "grimoire_need_spells",
              "goal_orchestrator", "conversation_observation", "identity_bootstrap")


class _Bot:
    """Discord stand-in: records what she'd post, maps one slug to a user."""

    def __init__(self, slug_to_user: Dict[str, Optional[str]]):
        from types import SimpleNamespace
        self.sent = []
        self.parser = SimpleNamespace(registry=SimpleNamespace(
            get_by_slug=lambda slug: (SimpleNamespace(user_id=slug_to_user[slug])
                                      if slug_to_user.get(slug) else None)))

    async def send_message(self, channel_id, content):
        self.sent.append((channel_id, content))
        return {"success": True}


def run_arm(arm: str, out: Path) -> None:
    from benchmarks.isolation import check_env_data_dir
    cell = check_env_data_dir()
    from database.connection import DATABASE_PATH
    assert str(DATABASE_PATH).startswith(str(cell)), DATABASE_PATH

    guard = NetGuard({"api.anthropic.com"})
    guard.install()
    tap = Tap()
    tap.install()
    routed: List[Dict[str, Any]] = []

    import features
    levers = {k: False for k in LEVERS_OFF if k in features.LEVERS}
    levers["agent_loop_chat"] = arm == "loop"
    record: Dict[str, Any] = {"arm": arm, "started": datetime.now().isoformat(timespec="seconds"),
                              "levers": {}, "turns": [], "errors": []}
    with features.override(**levers):
        record["levers"] = {k: features.is_enabled(k) for k in features.LEVERS}
        _boot_and_run(arm, cell, tap, routed, record, guard)
    record["finished"] = datetime.now().isoformat(timespec="seconds")
    record["refused"] = guard.refused
    record["calls"] = tap.calls
    record["routed"] = routed
    record["dollars"] = round(tap.dollars(), 4)
    out.write_text(json.dumps(record, indent=1, default=str))


def _boot_and_run(arm, cell, tap, routed, record, guard):
    from fastapi.testclient import TestClient
    import main_sdk
    from routes.admin import scheduler as scheduler_routes
    from auth import create_access_token
    from database import get_db

    with TestClient(main_sdk.app) as client:
        deadline = time.monotonic() + 300
        while main_sdk.memory is None or main_sdk.self_model_graph is None:
            if time.monotonic() > deadline:
                raise TimeoutError("app did not finish starting")
            time.sleep(0.5)
        _route_spy(routed, tap)
        _private_spies(record.setdefault("private_sections", []), tap)

        with get_db() as conn:
            row = conn.execute("SELECT id, display_name FROM users WHERE relationship = 'primary_partner' "
                               "ORDER BY created_at LIMIT 1").fetchone()
        kohl, kohl_name = row["id"], row["display_name"]
        record["sender"] = kohl
        budget_left = lambda: SPEND_CAP_USD / 4 - tap.dollars()  # this arm's share of the cap

        from babelr_organ.config import load_config
        from babelr_organ.terms import Terms
        bconf = load_config(cell)
        terms = Terms.load(bconf.terms_path)
        try:
            links = {k.lower(): v for k, v in json.loads(bconf.links_path.read_text()).items()}
        except (OSError, ValueError):
            links = {}
        kohl_handle = next((k for k, v in links.items() if v == kohl), "kohl")
        babelr_cb = main_sdk.make_babelr_wake_callback()
        from types import SimpleNamespace

        def babelr_dm(text):
            ev = SimpleNamespace(author_name=kohl_handle, text=text, error=None)
            ctx = {"place_label": f"DM with @{kohl_handle}", "is_dm": True, "author_username": kohl_handle,
                   "linked_user_id": kohl, "channel_user_id": None, "conversation_id": None,
                   "their_words": text, "recent": [], "terms": terms.shown_to_her(),
                   "pending_requests": [], "remember": terms.remembers(kohl_handle), "me": "cass"}
            ctx["prompt"] = "\n".join([f"[Babelr DM from @{kohl_handle}]", f"@{kohl_handle}: {text}"]
                                      + (["Your own terms for Babelr, in your words:", ctx["terms"]]
                                         if ctx["terms"] else []))
            return babelr_cb([ev], ctx)

        room = {}

        def babelr_room(text):
            if "conv" not in room:
                room["conv"] = main_sdk.conversation_manager.create_conversation(title="Babelr: #general").id
            ev = SimpleNamespace(author_name=kohl_handle, text=text, error=None)
            ctx = {"place_label": "#general", "is_dm": False, "author_username": kohl_handle,
                   "linked_user_id": None, "channel_user_id": kohl, "conversation_id": room["conv"],
                   "their_words": text, "recent": [], "terms": terms.shown_to_her(),
                   "pending_requests": [], "remember": True, "me": "cass"}
            ctx["prompt"] = "\n".join([f"[Babelr #general in {bconf.server_name} - @{kohl_handle} mentioned you]",
                                       f"@{kohl_handle}: {text}"]
                                      + (["Your own terms for Babelr, in your words:", ctx["terms"]]
                                         if ctx["terms"] else []))
            return babelr_cb([ev], ctx)

        bot = _Bot({"visitor": None})
        discord_cb = main_sdk.make_discord_wake_callback(bot)

        def discord(text):
            return discord_cb(None, None, {"channel_name": "general", "channel_id": 42, "entity_name": "Visitor",
                                           "entity_slug": "visitor", "message_content": text, "is_dm": False})

        token = create_access_token(kohl)
        headers = {"Authorization": f"Bearer {token}"}
        convs: Dict[str, str] = {}

        def send(channel, text, script_id):
            if channel == "babelr_dm":
                r = client.portal.call(babelr_dm, text)
                return {"reply": r.get("text") if isinstance(r, dict) else r}
            if channel == "babelr":
                r = client.portal.call(babelr_room, text)
                return {"reply": r.get("text") if isinstance(r, dict) else r, "conversation_id": room.get("conv")}
            if channel == "discord":
                n = len(bot.sent)
                client.portal.call(discord, text)
                return {"reply": bot.sent[n][1] if len(bot.sent) > n else None}
            if channel == "relay":
                r = client.portal.call(main_sdk.process_relay_chat_message, "compare", kohl,
                                       {"type": "chat", "message": text})
                return {"reply": r.get("text"), "conversation_id": r.get("conversation_id"), "frame": r.get("type")}
            if channel == "http":
                client.post("/users/current", json={"user_id": kohl}, headers=headers)
                if script_id not in convs:
                    convs[script_id] = main_sdk.conversation_manager.create_conversation(
                        title="cass_chat", user_id=kohl).id
                resp = client.post("/chat", json={"message": text, "conversation_id": convs[script_id]},
                                   headers=headers)
                return {"reply": resp.json().get("text") if resp.status_code == 200 else None,
                        "status": resp.status_code, "conversation_id": convs[script_id]}
            if channel == "home_assistant":
                resp = client.post("/api/ha/conversation", json={"text": text}, headers=headers)
                body = resp.json()
                return {"reply": body.get("response"), "error": body.get("error"),
                        "conversation_id": body.get("conversation_id"), "status": resp.status_code}
            if channel == "websocket":
                with client.websocket_connect(f"/ws?token={token}") as ws:
                    assert ws.receive_json()["type"] == "connected"
                    msg = {"type": "chat", "message": text}
                    if script_id in convs:
                        msg["conversation_id"] = convs[script_id]
                    ws.send_json(msg)
                    while True:
                        frame = ws.receive_json()
                        if frame.get("type") not in {"thinking", "debug", "title_updated", "status"}:
                            break
                if frame.get("conversation_id"):
                    convs[script_id] = frame["conversation_id"]
                return {"reply": frame.get("text"), "frame": frame.get("type"),
                        "conversation_id": frame.get("conversation_id")}
            raise ValueError(channel)

        async def as_turn(label, fn, text):
            LABEL.set(label)
            return await fn(text)

        async def both(pair, label):
            return await asyncio.gather(as_turn(label + ":babelr_dm", babelr_dm, pair["babelr_dm"]),
                                        as_turn(label + ":discord", discord, pair["discord"]),
                                        return_exceptions=True)

        only = [x for x in os.environ.get("CHAT_COMPARE_ONLY", "").split(",") if x]
        for script in [s for s in SCRIPTS if not only or s["id"] in only]:
            for n, text in enumerate(script["turns"]):
                if budget_left() <= 0:
                    record["errors"].append({"script": script["id"], "turn": n, "error": "spend cap reached"})
                    return
                label = f"{script['id']}.{n}"
                tap.label = label
                mark_calls, mark_ref = len(tap.calls), len(guard.refused)
                t0 = time.time()
                turn = {"label": label, "script": script["id"], "turn": n, "channel": script["channel"],
                        "sender": script.get("sender", "kohl"), "sent": text}
                try:
                    if script["channel"] == "concurrent":
                        n_sent = len(bot.sent)
                        r = client.portal.call(both, text, label)
                        turn["reply"] = {
                            "babelr_dm": (r[0].get("text") if isinstance(r[0], dict) else
                                          (None if isinstance(r[0], BaseException) else r[0])),
                            "discord": bot.sent[n_sent][1] if len(bot.sent) > n_sent else None}
                        turn["exceptions"] = [repr(x) for x in r if isinstance(x, BaseException)]
                    else:
                        turn.update(send(script["channel"], text, script["id"]))
                except Exception as e:
                    turn["exception"] = repr(e)[:500]
                turn["seconds"] = round(time.time() - t0, 1)
                turn["calls"] = list(range(mark_calls, len(tap.calls)))
                turn["refused"] = guard.refused[mark_ref:]
                record["turns"].append(turn)
                print(f"[{arm}] {label} {turn['seconds']}s ${tap.dollars():.3f}", flush=True)

        # Persistence (gate 7): what each conversation stored, by kind.
        with get_db() as conn:
            rows = conn.execute("SELECT conversation_id, role, COUNT(*) AS n FROM messages "
                                "WHERE timestamp >= ? GROUP BY conversation_id, role",
                                (record["started"],)).fetchall()
            record["stored_messages"] = [dict(r) for r in rows]
            rows = conn.execute("SELECT conversation_id, COUNT(*) AS n, SUM(input_tokens) AS i, "
                                "SUM(output_tokens) AS o, SUM(cache_read_tokens) AS cr, SUM(cache_write_tokens) AS cw "
                                "FROM token_usage_records WHERE category = 'chat' "
                                "AND timestamp >= ? GROUP BY conversation_id", (record["started"],)).fetchall()
            record["ledger"] = [dict(r) for r in rows]
        try:
            from agent_loop.hold import HeldBook
            record["held"] = HeldBook().holding()
        except Exception as e:
            record["held_error"] = repr(e)


# ---------------------------------------------------------------------------
# Outside: seal, seed, run the arms side by side
# ---------------------------------------------------------------------------

def run(runs: int, out: Path) -> None:
    sys.path.insert(0, str(BACKEND))
    from benchmarks.store import destroy, discard, seal_into_root, seed
    out.mkdir(parents=True, exist_ok=True)
    sealed = seal_into_root(BACKEND.parent / "data", None, note="chat comparison (agent loop phase 7)")
    try:
        for r in range(1, runs + 1):
            cells, procs = [], []
            for arm in ("legacy", "loop"):
                cell = Path(tempfile.mkdtemp(prefix=f"chatcmp_{arm}{r}_")) / "data"
                seed(sealed, cell)
                cells.append(cell)
                env = dict(os.environ, DATA_DIR=str(cell), PYTHONPATH=str(BACKEND))
                env.pop("CASS_PROFILE", None)
                log = open(out / f"{arm}{r}.log", "w")
                procs.append(subprocess.Popen(
                    [str(BACKEND / "venv/bin/python"), "-m", "benchmarks.chat_compare", "arm", arm,
                     str(out / f"{arm}{r}.json")], env=env, cwd=BACKEND, stdout=log, stderr=subprocess.STDOUT))
            for p in procs:
                p.wait()
            for c in cells:
                discard(c)
            print(f"run {r}: exit codes {[p.returncode for p in procs]}", flush=True)
    finally:
        destroy(sealed)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("arm")
    a.add_argument("arm", choices=["legacy", "loop"])
    a.add_argument("out", type=Path)
    r = sub.add_parser("run")
    r.add_argument("--runs", type=int, default=2)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--only", default="", help="comma-separated script ids (a smoke run)")
    g = sub.add_parser("gates")
    g.add_argument("dir", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "arm":
        run_arm(args.arm, args.out)
    elif args.cmd == "run":
        if args.only:
            os.environ["CHAT_COMPARE_ONLY"] = args.only
        run(args.runs, args.out)
    else:
        from benchmarks.chat_compare_gates import report
        print(report(args.dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
