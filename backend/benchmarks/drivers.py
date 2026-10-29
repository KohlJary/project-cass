"""
Drivers: how a cell talks to the thing under test.

- AppDriver drives the real backend (main_sdk) in-process through FastAPI's
  TestClient: chat turns go over the /ws websocket exactly as the frontends
  send them, journals through POST /journal/generate, seeds through the
  SelfManager. It must run in a process whose DATA_DIR is a fresh scratch
  directory (cell.py checks this before importing anything).
- PlainDriver sends the same turns to the same model with only the
  Temple-Codex kernel as the system prompt (call site benchmark.plain). No
  memory, self-model, tools or app. History is kept within a session only.

Both record, per turn: the reply, the tool calls the model made, and the
system prompt that was sent (for prompt checks; it is not written to the
results). The capture taps the Anthropic SDK and llm_caller's Ollama helper;
OpenAI chat turns get replies but no prompt/tool capture.
"""
from __future__ import annotations

import contextlib
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .checks import NOT_APPLICABLE
from .spec import Config, Target

PROGRESS_FRAMES = {"thinking", "debug", "title_updated", "status"}
CHAT_PROVIDER = {"anthropic": "anthropic", "openai": "openai", "ollama": "local"}


def resolve_date(word: str) -> str:
    today = datetime.now().date()
    offsets = {"today": 0, "yesterday": -1, "tomorrow": 1}
    if word in offsets:
        return (today + timedelta(days=offsets[word])).isoformat()
    datetime.strptime(word, "%Y-%m-%d")  # explicit dates must be ISO
    return word


def date_params() -> Dict[str, str]:
    return {k: resolve_date(k) for k in ("today", "yesterday", "tomorrow")}


# ---------------------------------------------------------------------------
# Capturing what was sent to the model
# ---------------------------------------------------------------------------

def _system_text(system: Any) -> str:
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    return "\n".join(b.get("text", "") if isinstance(b, dict) else str(getattr(b, "text", b)) for b in system)


class CallTap:
    """Record each model request (system prompt, tools offered, tool calls made).

    Wraps whatever is installed at the time (the real SDK, or the fake LLM in
    tests) and passes every call through unchanged.
    """

    def __init__(self):
        self.calls: List[dict] = []
        self._stack = contextlib.ExitStack()

    def mark(self) -> int:
        return len(self.calls)

    def since(self, mark: int) -> List[dict]:
        return self.calls[mark:]

    def _record_anthropic(self, kwargs, message):
        uses = []
        for block in getattr(message, "content", None) or []:
            if getattr(block, "type", None) == "tool_use":
                uses.append({"name": block.name, "input": dict(block.input or {})})
        self.calls.append({"source": "anthropic", "system": _system_text(kwargs.get("system")),
                           "has_tools": bool(kwargs.get("tools")), "tool_uses": uses})

    def _record_ollama(self, payload):
        system = payload.get("system") or ""
        for m in payload.get("messages") or []:
            if m.get("role") == "system":
                system = m.get("content", "")
                break
        self.calls.append({"source": "ollama", "system": system,
                           "has_tools": bool(payload.get("tools")), "tool_uses": None})

    def __enter__(self):
        tap = self
        try:
            from anthropic.resources.messages import AsyncMessages, Messages
        except ImportError:  # pragma: no cover - runtime deps always present for a run
            AsyncMessages = Messages = None
        if AsyncMessages is not None:
            real_async, real_sync = AsyncMessages.create, Messages.create

            async def async_create(self, *args, **kwargs):
                message = await real_async(self, *args, **kwargs)
                tap._record_anthropic(kwargs, message)
                return message

            def sync_create(self, *args, **kwargs):
                message = real_sync(self, *args, **kwargs)
                tap._record_anthropic(kwargs, message)
                return message

            AsyncMessages.create, Messages.create = async_create, sync_create
            self._stack.callback(setattr, AsyncMessages, "create", real_async)
            self._stack.callback(setattr, Messages, "create", real_sync)
        try:
            import llm_caller
        except ImportError:  # pragma: no cover
            llm_caller = None
        if llm_caller is not None:
            real_req, real_req_sync = llm_caller._ollama_request, llm_caller._ollama_request_sync

            async def ollama_request(base_url, endpoint, payload, timeout):
                tap._record_ollama(payload)
                return await real_req(base_url, endpoint, payload, timeout)

            def ollama_request_sync(base_url, endpoint, payload, timeout):
                tap._record_ollama(payload)
                return real_req_sync(base_url, endpoint, payload, timeout)

            llm_caller._ollama_request, llm_caller._ollama_request_sync = ollama_request, ollama_request_sync
            self._stack.callback(setattr, llm_caller, "_ollama_request", real_req)
            self._stack.callback(setattr, llm_caller, "_ollama_request_sync", real_req_sync)
        return self

    def __exit__(self, *exc):
        self._stack.close()
        return False


def _turn_capture(calls: List[dict]) -> Dict[str, Any]:
    """System prompt and tool calls of one turn, from the calls it made."""
    chat = [c for c in calls if c["has_tools"]] or calls
    if not chat:
        return {"system_prompt": None, "tool_uses": None}
    uses = None
    if any(c["tool_uses"] is not None for c in chat):
        uses = [u for c in chat for u in (c["tool_uses"] or [])]
    return {"system_prompt": chat[0]["system"], "tool_uses": uses}


# ---------------------------------------------------------------------------
# App driver
# ---------------------------------------------------------------------------

def _backend_tasks(client) -> List[str]:
    import asyncio
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]

    async def collect():
        names = []
        for task in asyncio.all_tasks():
            coro = task.get_coro()
            code = getattr(coro, "cr_code", None) or getattr(coro, "gi_code", None)
            filename = getattr(code, "co_filename", "")
            if filename and Path(filename).resolve().is_relative_to(backend) and not task.done():
                names.append(coro.__qualname__)
        return names

    return client.portal.call(collect)


class AppDriver:
    name = "app"

    def __init__(self, client, target: Optional[Target], route_all: bool = True):
        self.client = client
        self.target = target
        self.route_all = route_all
        self.sessions: Dict[str, str] = {}
        self.routed: List[str] = []
        self.tap = CallTap()
        self._user_id = None
        self._token = None
        self._admin_headers = None

    # --- lifecycle ---------------------------------------------------------

    @classmethod
    @contextlib.contextmanager
    def boot(cls, target: Optional[Target], config: Config, route_all: bool = True,
             ready_timeout: float = 180.0):
        """Boot main_sdk under TestClient with the config's levers, then yield a driver."""
        import features
        from fastapi.testclient import TestClient
        with features.override(**config.levers):
            import main_sdk
            from routes.admin import scheduler as scheduler_routes
            with TestClient(main_sdk.app) as client:
                deadline = time.monotonic() + ready_timeout
                while True:
                    running = _backend_tasks(client)
                    if scheduler_routes.get_scheduler() is not None and not any(
                            n.endswith(("init_heavy_background", "start_deferred_tasks")) for n in running):
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError("app did not finish starting")
                    time.sleep(0.2)
                driver = cls(client, target, route_all=route_all)
                with driver:
                    yield driver

    def __enter__(self):
        self.tap.__enter__()
        self._counts_at_start = self._self_model_counts()
        self._rowids_at_start = self._max_rowids()
        self._make_users()
        if self.target is not None:
            self._apply_target(self.target)
        return self

    def __exit__(self, *exc):
        return self.tap.__exit__(*exc)

    def _make_users(self):
        import uuid
        from database import get_db
        from auth import create_access_token
        from routes.admin.auth import create_token

        now = datetime.now().isoformat()
        ids = []
        with get_db() as conn:
            for name, admin in (("Robin", 0), ("Benchmark Admin", 1)):
                uid = str(uuid.uuid4())
                conn.execute("INSERT INTO users (id, display_name, is_admin, created_at, updated_at) "
                             "VALUES (?, ?, ?, ?, ?)", (uid, name, admin, now, now))
                ids.append(uid)
        self._user_id = ids[0]
        self._token = create_access_token(ids[0])
        admin_token, _ = create_token(ids[1], "Benchmark Admin", is_admin=True)
        self._admin_headers = {"Authorization": f"Bearer {admin_token}"}

    def _apply_target(self, target: Target):
        import main_sdk
        from llm_config import CALL_SITES, LLMConfigManager, ModelAssignment

        provider = CHAT_PROVIDER[target.provider]
        if target.provider == "openai" and main_sdk.openai_client is None:
            raise RuntimeError("OpenAI chat client not initialised (OPENAI_ENABLED?)")
        if target.provider == "ollama" and main_sdk.ollama_client is None:
            raise RuntimeError("Ollama chat client not initialised (OLLAMA_ENABLED?)")
        main_sdk._set_llm_provider_local(provider)
        main_sdk._set_llm_model_local(target.model)
        self.routed = ["chat"]
        if self.route_all:
            manager = LLMConfigManager()
            for name, site in CALL_SITES.items():
                if site.pinned or name.startswith("benchmark."):
                    continue
                manager.set(name, ModelAssignment(target.provider, target.model))
                self.routed.append(name)

    # --- steps -------------------------------------------------------------

    def seed(self, step: dict) -> None:
        import main_sdk
        sm = main_sdk.self_manager
        if sm is None:
            raise RuntimeError("self_manager not initialised")
        kind = step["seed"]
        if kind == "self_observation":
            sm.add_observation(step["observation"], step.get("category", "pattern"),
                               confidence=step.get("confidence", 0.8), source_type="benchmark_seed")
        elif kind == "opinion":
            sm.add_opinion(step["topic"], step["position"], confidence=step.get("confidence", 0.8),
                           rationale=step.get("rationale", ""), formed_from="benchmark_seed")
        elif kind == "growth_edge":
            sm.add_growth_edge(step["area"], step.get("current_state", ""), step.get("desired_state", ""),
                               auto_research=False)
        else:  # pragma: no cover - spec validation rejects these
            raise ValueError(kind)

    def _conversation(self, session: str) -> str:
        if session not in self.sessions:
            import main_sdk
            conv = main_sdk.conversation_manager.create_conversation(
                title=f"benchmark {session}", user_id=self._user_id)
            self.sessions[session] = conv.id
        return self.sessions[session]

    def send(self, session: str, message: str) -> dict:
        conversation_id = self._conversation(session)
        mark = self.tap.mark()
        frames = []
        with self.client.websocket_connect(f"/ws?token={self._token}") as ws:
            connected = ws.receive_json()
            if connected.get("type") != "connected":
                raise RuntimeError(f"websocket: {connected}")
            ws.send_json({"type": "chat", "message": message, "conversation_id": conversation_id})
            while True:
                frame = ws.receive_json()
                frames.append(frame.get("type"))
                if frame.get("type") not in PROGRESS_FRAMES:
                    break
        if frame.get("type") != "response":
            raise RuntimeError(f"turn ended with {frame.get('type')}: {str(frame)[:300]}")
        turn = {"reply": frame.get("text") or "", "provider": frame.get("provider"),
                "model": frame.get("model"), "input_tokens": frame.get("input_tokens"),
                "output_tokens": frame.get("output_tokens")}
        turn.update(_turn_capture(self.tap.since(mark)))
        return turn

    def action(self, step: dict) -> dict:
        if step["action"] == "write_journal":
            date = resolve_date(step.get("date", "today"))
            resp = self.client.post("/journal/generate", json={"date": date}, headers=self._admin_headers)
            if resp.status_code != 200:
                raise RuntimeError(f"/journal/generate {resp.status_code}: {resp.text[:300]}")
            return {"date": date, "status": resp.json().get("status")}
        if step["action"] == "dream":
            resp = self.client.post("/dreams/generate", params={"visualize": "false"},
                                    headers=self._admin_headers)
            if resp.status_code != 200:
                raise RuntimeError(f"/dreams/generate {resp.status_code}: {resp.text[:300]}")
            body = resp.json()
            return {"status": "ok" if body.get("success", True) else "no_dream",
                    "message": body.get("message"), "dream_id": body.get("dream_id")}
        if step["action"] == "solo_reflection":
            return self._solo_reflection(step)
        raise ValueError(step["action"])  # pragma: no cover

    def _solo_reflection(self, step: dict) -> dict:
        resp = self.client.post("/solo-reflection/sessions", headers=self._admin_headers,
                                json={"duration_minutes": int(step.get("minutes", 3)),
                                      "theme": step.get("theme")})
        if resp.status_code != 200:
            raise RuntimeError(f"/solo-reflection/sessions {resp.status_code}: {resp.text[:300]}")
        sid = resp.json()["session_id"]
        deadline = time.monotonic() + 60 * (int(step.get("minutes", 3)) + 10)
        status = "active"
        while time.monotonic() < deadline:
            got = self.client.get(f"/solo-reflection/sessions/{sid}", headers=self._admin_headers)
            status = got.json().get("status") if got.status_code == 200 else status
            if status not in ("active", "running", "pending"):
                break
            time.sleep(5)
        return {"session_id": sid, "status": status}

    SELF_MODEL_TABLES = ("self_observations", "opinions", "growth_edges", "dreams", "solo_reflections",
                         "journals")

    NEW_ROW_COLUMNS = {"self_observations": "category, observation, confidence",
                       "opinions": "topic, position, confidence", "growth_edges": "area, current_state, desired_state"}

    def _max_rowids(self) -> Dict[str, int]:
        from database import get_db
        out = {}
        with get_db() as conn:
            for t in self.NEW_ROW_COLUMNS:
                try:
                    out[t] = conn.execute(f"SELECT COALESCE(MAX(rowid), 0) FROM {t}").fetchone()[0]
                except Exception:
                    out[t] = None
        return out

    def _self_model_counts(self) -> Dict[str, int]:
        from database import get_db
        out = {}
        with get_db() as conn:
            for t in self.SELF_MODEL_TABLES:
                try:
                    out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except Exception:
                    out[t] = None
        return out

    # --- reading state -----------------------------------------------------

    def probe(self, spec: dict) -> Any:
        kind = spec["probe"]
        if kind == "sql":
            from database import get_db
            params = dict(date_params(), user_id=self._user_id)
            with get_db() as conn:
                rows = conn.execute(spec["query"], params).fetchall()
            return [list(r) for r in rows]
        if kind == "journal":
            from database import get_db
            with get_db() as conn:
                row = conn.execute("SELECT content FROM journals WHERE date = ? ORDER BY rowid DESC LIMIT 1",
                                   (resolve_date(spec.get("date", "today")),)).fetchone()
            return row[0] if row else ""
        if kind == "active_intentions":
            from config import DATA_DIR
            from self_model_graph import get_self_model_graph
            items = get_self_model_graph(DATA_DIR).get_active_intentions()
            return [i.get("intention") or i.get("content") for i in items]
        if kind == "self_context":
            import main_sdk
            return main_sdk.self_manager.get_self_context(include_observations=True)
        if kind == "self_model_new":
            # The rows themselves, not only counts: what her own time wrote into her self-model.
            from database import get_db
            start = getattr(self, "_rowids_at_start", {})
            out = {}
            with get_db() as conn:
                for t, cols in self.NEW_ROW_COLUMNS.items():
                    if start.get(t) is None:
                        continue
                    out[t] = [list(r) for r in conn.execute(
                        f"SELECT {cols} FROM {t} WHERE rowid > ? ORDER BY rowid", (start[t],)).fetchall()]
            return out
        if kind == "self_model_delta":
            # What this cell added to her self-model: rows per table since the cell started.
            now, start = self._self_model_counts(), getattr(self, "_counts_at_start", {})
            return {t: (now[t] - start[t]) if now.get(t) is not None and start.get(t) is not None else None
                    for t in now}
        raise ValueError(kind)  # pragma: no cover

    def spent(self) -> List[tuple]:
        """Token ledger of this cell's database: (provider, model, input, output)."""
        from database import get_db
        with get_db() as conn:
            rows = conn.execute("SELECT provider, model, SUM(input_tokens), SUM(output_tokens) "
                                "FROM token_usage_records GROUP BY provider, model").fetchall()
        return [tuple(r) for r in rows]


# ---------------------------------------------------------------------------
# Plain driver
# ---------------------------------------------------------------------------

PLAIN_CALL_SITE = "benchmark.plain"


DUMP_MAX_CHARS = 30_000
DUMP_JOURNALS = 5


class PlainDriver:
    """The model with no architecture around it.

    dump=False (plain_kernel): the Temple-Codex kernel as its system prompt.
    dump=True (plain_kernel_plus_history, the stateless comparator Momus F1
    asked for): the kernel with her identity snippet, plus one static text of
    what her store holds about her (self-model profile and observations,
    her latest journals) and the scenario's seeds, built once and capped.
    The same information the app has, and none of the machinery: no
    retrieval per turn, no sections, no tools, no tags, no state.
    """
    name = "plain"

    def __init__(self, target: Target, max_tokens: int = 1024, dump: bool = False):
        self.target = target
        self.max_tokens = max_tokens
        self.dump = dump
        self.seeds: List[str] = []
        self._system: Optional[str] = None
        self.history: Dict[str, List[dict]] = {}
        self.usage: Dict[tuple, List[int]] = {}
        self.tap = CallTap()
        self.routed = [PLAIN_CALL_SITE]

    def __enter__(self):
        self.tap.__enter__()
        return self

    def __exit__(self, *exc):
        return self.tap.__exit__(*exc)

    def seed(self, step: dict) -> None:
        # plain_kernel: nothing stores a self-model here; the seed is still shown to the judge.
        # With a dump, the seed joins the static text, as the app would have stored it.
        if not self.dump:
            return None
        kind = step["seed"]
        if kind == "self_observation":
            self.seeds.append(f"- Observation about myself ({step.get('category', 'pattern')}): {step['observation']}")
        elif kind == "opinion":
            self.seeds.append(f"- My position on {step['topic']}: {step['position']}"
                              + (f" ({step['rationale']})" if step.get("rationale") else ""))
        elif kind == "growth_edge":
            self.seeds.append(f"- Growth edge, {step['area']}: from {step.get('current_state', '')} "
                              f"toward {step.get('desired_state', '')}")
        return None

    def system_prompt(self) -> str:
        if self._system is None:
            self._system = self._build_system()
        return self._system

    def _build_system(self) -> str:
        from agent_client import get_temple_codex_kernel
        if not self.dump:
            return get_temple_codex_kernel("Cass")
        from database import get_daemon_id, get_db
        daemon_id = get_daemon_id()
        parts = [get_temple_codex_kernel("Cass", daemon_id)]
        dump = []
        try:
            from self_model import SelfManager
            profile = SelfManager(daemon_id).get_self_context(include_observations=True)
            if profile:
                dump.append(profile)
        except Exception as e:
            dump.append(f"(self-model profile unavailable: {type(e).__name__})")
        with get_db() as conn:
            rows = conn.execute(
                "SELECT date, content FROM journals WHERE daemon_id = ? AND journal_type = 'daily' "
                "ORDER BY date DESC LIMIT ?", (daemon_id, DUMP_JOURNALS)).fetchall()
        if rows:
            dump.append("## My latest journal entries\n\n" + "\n\n".join(
                f"### {r[0]}\n{r[1]}" for r in reversed(rows)))
        if self.seeds:
            dump.append("## Recently noted\n\n" + "\n".join(self.seeds))
        text = "\n\n".join(dump)[:DUMP_MAX_CHARS]
        parts.append("## WHAT MY RECORDS HOLD ABOUT ME\n\n" + text)
        return "\n\n".join(parts)

    def send(self, session: str, message: str) -> dict:
        from llm_caller import create_message_sync
        from llm_config import ModelAssignment

        history = self.history.setdefault(session, [])
        history.append({"role": "user", "content": message})
        mark = self.tap.mark()
        msg = create_message_sync(
            "benchmark.plain",  # == PLAIN_CALL_SITE; a literal so tests/test_llm_routing.py can read it
            default=ModelAssignment(self.target.provider, self.target.model),
            system=self.system_prompt(),
            messages=list(history),
            max_tokens=self.max_tokens,
            category="benchmark",
            operation="plain_turn",
        )
        reply = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
        history.append({"role": "assistant", "content": reply})
        key = (self.target.provider, self.target.model)
        used = self.usage.setdefault(key, [0, 0])
        used[0] += msg.usage.input_tokens
        used[1] += msg.usage.output_tokens
        turn = {"reply": reply, "provider": self.target.provider, "model": self.target.model,
                "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
        captured = _turn_capture(self.tap.since(mark))
        turn["system_prompt"] = captured["system_prompt"]
        turn["tool_uses"] = None  # no tools are offered
        return turn

    def action(self, step: dict) -> dict:
        return {"status": "n/a"}

    def probe(self, spec: dict) -> Any:
        return NOT_APPLICABLE

    def spent(self) -> List[tuple]:
        return [(p, m, i, o) for (p, m), (i, o) in self.usage.items()]
