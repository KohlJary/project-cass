"""
One research pipeline (#60): one queue, one runner, a model per step through
routing, one web-search interface.

Every test uses the fake LLM and a fake search backend; nothing reaches the
network. Each old entry point is driven and checked to land in the one queue,
run through ResearchRunner (only the runner records `models` on a result),
and store its output where it did before (wiki pages for wiki steps; the
session runner's own records for sessions).
"""
import asyncio
import importlib.util
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from llm_config import CALL_SITES, LLMConfigManager, ModelAssignment
from research_pipeline import STEPS, ResearchRunner, get_research_pipeline, search as rsearch
from research_pipeline.search import SearchHit, SearchResponse, use_backends
from wiki.research import (
    ResearchQueue,
    ResearchTask,
    TaskType,
    create_task_id,
)
from wiki.scheduler import ResearchScheduler, SchedulerConfig
from wiki.storage import WikiStorage

OLLAMA_DEFAULT = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")
HAIKU = "claude-haiku-4-5-20251001"


def _has(mod):
    return importlib.util.find_spec(mod) is not None


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeSearch:
    """A search backend that answers from memory and records the queries."""

    def __init__(self, name="fake", fail=False):
        self.name = name
        self.fail = fail
        self.queries = []

    async def search(self, query, num_results=10, **opts):
        self.queries.append(query)
        if self.fail:
            return SearchResponse(False, self.name, [], error="down")
        return SearchResponse(True, self.name, [
            SearchHit(title=f"About {query}", url="https://example.org/a",
                      snippet=f"{query} is a thing worth knowing.", source="Example"),
        ], answer=f"{query}: an answer")


class FakeSessionManager:
    def __init__(self):
        self.sessions = {}

    def get_session(self, session_id):
        return self.sessions.get(session_id)


class FakeLegacyRunner:
    """Stands in for ResearchSessionRunner: start_session returns at once and
    the session loop runs as a background task, as the real one does."""

    def __init__(self):
        self.use_haiku = True
        self.haiku_model = HAIKU
        self.ollama_model = "llama3.1:8b-instruct-q8_0"
        self.session_manager = FakeSessionManager()
        self.started = []
        self._running = False
        self._current_task = None

    @property
    def is_running(self):
        return self._running

    async def start_session(self, duration_minutes=30, focus=None, **kwargs):
        sid = f"rs_{len(self.started) + 1}"
        self.started.append(dict(duration_minutes=duration_minutes, focus=focus, **kwargs))
        self._running = True

        async def loop():
            await asyncio.sleep(0)
            self.session_manager.sessions[sid] = {
                "session_id": sid, "status": "completed",
                "summary": f"Researched {focus}", "findings_summary": "- one finding",
            }
            self._running = False

        self._current_task = asyncio.ensure_future(loop())
        return SimpleNamespace(session_id=sid, duration_limit_minutes=duration_minutes,
                               focus_description=focus, mode=kwargs.get("mode", "explore"))


class _OllamaOnlyFake:
    """Fallback for the fast CI job (no anthropic SDK, so tests/fakes/llm.py
    can't install): answers llm_caller's Ollama requests, which is every call
    the wiki steps make by default."""

    def __init__(self, monkeypatch):
        import llm_caller
        self.calls = []
        self._queue = []

        async def fake(base_url, endpoint, payload, timeout):
            text = self._queue.pop(0) if self._queue else "OK"
            self.calls.append(SimpleNamespace(source="ollama", model=payload.get("model"), kwargs=payload))
            return {"response": text, "prompt_eval_count": 10, "eval_count": 5}

        monkeypatch.setattr(llm_caller, "_ollama_request", fake)

    def queue_text(self, text):
        self._queue.append(text)
        return self


@pytest.fixture
def llm(request, monkeypatch):
    """tests/fakes/llm.py's fake_llm where the SDKs are installed, else an
    Ollama-only fake. Either way nothing reaches a model."""
    if _has("anthropic"):
        return request.getfixturevalue("fake_llm")
    return _OllamaOnlyFake(monkeypatch)


@pytest.fixture
def search_backend():
    backend = FakeSearch()
    with use_backends([backend]):
        yield backend


@pytest.fixture
def wiki_scheduler(tmp_path):
    storage = WikiStorage(str(tmp_path / "wiki"), git_enabled=False)
    sched = ResearchScheduler(storage, ResearchQueue(), SchedulerConfig(min_delay_between_tasks=0))
    import wiki
    previous = wiki.get_scheduler()
    wiki.set_scheduler(sched)
    yield sched
    wiki.set_scheduler(previous)


def _red_link(queue, target="Tidal Locking", priority=0.9):
    task = ResearchTask(task_id=create_task_id(), task_type=TaskType.RED_LINK, target=target,
                        context="test", priority=priority)
    queue.add(task)
    return task


def _row(task_id):
    from database import get_db, json_deserialize
    with get_db() as conn:
        row = conn.execute("SELECT status, result_json, params_json, task_type FROM research_tasks WHERE id = ?",
                           (task_id,)).fetchone()
    return (row[0], json_deserialize(row[1]) if row[1] else None,
            json_deserialize(row[2]) if row[2] else None, row[3])


def _session_rows():
    from database import get_db
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM research_tasks WHERE task_type = 'session'").fetchall()
    return [_row(r[0]) for r in rows]


async def _drain():
    """Let background session watchers finish."""
    for _ in range(5):
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Steps and routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_every_step_uses_registered_call_sites():
    for step in STEPS.values():
        for site in step.call_sites:
            assert site in CALL_SITES, f"{step.name} uses unregistered call site {site}"


@pytest.mark.unit
def test_step_defaults_are_todays_models():
    """No override: each step resolves to the model it ran before #60."""
    from research_pipeline import resolve_step_models
    wiki_models = resolve_step_models(STEPS["red_link"])
    assert wiki_models == {"wiki.page_content": f"ollama:{OLLAMA_DEFAULT}"}
    assert resolve_step_models(STEPS["deepening"]) == {
        "wiki.resynthesis": f"ollama:{OLLAMA_DEFAULT}",
        "wiki.resynthesis_validation": f"ollama:{OLLAMA_DEFAULT}",
    }
    legacy = resolve_step_models(STEPS["session.legacy"],
                                 {"session.legacy": ModelAssignment("anthropic", HAIKU)})
    assert legacy == {"session.legacy": f"anthropic:{HAIKU}"}


@pytest.mark.unit
def test_research_budget_counting_unchanged():
    """The steps call the same sites as before, so the gate counts the same:
    of the research steps' call sites only these were counted on main."""
    pytest.importorskip("anthropic")
    from scheduler.budget import BUDGET_COUNTED_CALL_SITES
    sites = {s for step in STEPS.values() for s in step.call_sites}
    assert sites & BUDGET_COUNTED_CALL_SITES == {
        "wiki.resynthesis", "wiki.resynthesis_validation", "session.legacy"}


# ---------------------------------------------------------------------------
# Done-when: a queued task runs end to end, model per step from config,
# output in the wiki
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_queued_red_link_runs_end_to_end_with_routed_model(llm, search_backend, wiki_scheduler):
    LLMConfigManager().set("wiki.page_content", ModelAssignment("ollama", "qwen2.5:14b"))
    llm.queue_text("# Tidal Locking\n\nA body shows one face to its partner. See [[Orbital Resonance]].")
    task = _red_link(wiki_scheduler.queue)

    report = asyncio.run(wiki_scheduler.run_single_task())

    assert report.tasks_completed == 1
    assert search_backend.queries == ["Tidal Locking"]
    assert [c.model for c in llm.calls] == ["qwen2.5:14b"]
    page = wiki_scheduler.storage.read("Tidal Locking")
    assert page is not None and "one face" in page.content
    status, result, _params, _type = _row(task.task_id)
    assert status == "completed"
    assert result["models"] == {"wiki.page_content": "ollama:qwen2.5:14b"}
    # the follow-up red link was queued, as before
    assert wiki_scheduler.queue.exists("Orbital Resonance", TaskType.RED_LINK)


@pytest.mark.unit
def test_red_link_without_override_runs_todays_model(llm, search_backend, wiki_scheduler):
    llm.queue_text("# Comet\n\nIce and dust.")
    task = _red_link(wiki_scheduler.queue, "Comet")
    asyncio.run(wiki_scheduler.run_single_task(task.task_id))
    assert llm.calls[0].source.startswith("ollama")
    assert llm.calls[0].model == OLLAMA_DEFAULT
    assert wiki_scheduler.storage.read("Comet") is not None


# ---------------------------------------------------------------------------
# Wiki entry points all run through the one runner
# ---------------------------------------------------------------------------

def _assert_ran_through_runner(task_id):
    status, result, _p, _t = _row(task_id)
    assert status == "completed", status
    assert "models" in result, "result was not produced by ResearchRunner"


@pytest.mark.unit
def test_run_batch_and_batch_by_type(llm, search_backend, wiki_scheduler):
    a = _red_link(wiki_scheduler.queue, "Alpha")
    b = _red_link(wiki_scheduler.queue, "Beta", priority=0.8)
    report = asyncio.run(wiki_scheduler.run_batch(max_tasks=1))
    assert report.tasks_completed == 1
    _assert_ran_through_runner(a.task_id)
    report = asyncio.run(wiki_scheduler.run_batch_by_type(TaskType.RED_LINK, max_tasks=1))
    assert report.session_type == "batch_red_link" and report.tasks_completed == 1
    _assert_ran_through_runner(b.task_id)
    assert {"Alpha", "Beta"} <= {p.name for p in wiki_scheduler.storage.list_pages()}


@pytest.mark.unit
def test_autonomous_research_job_runs_through_runner(llm, search_backend, wiki_scheduler):
    from scheduler.handlers import autonomous_research_handler
    task = _red_link(wiki_scheduler.queue, "Gamma")
    res = asyncio.run(autonomous_research_handler(scheduler=wiki_scheduler, mode="batched", max_tasks=1))
    assert res.success, res.message
    _assert_ran_through_runner(task.task_id)


@pytest.mark.unit
def test_research_run_batch_action_runs_through_runner(llm, search_backend, wiki_scheduler):
    """research.run_batch: the research_synthesis spell, phase queue and
    Synkratos dispatch wiki research through this action."""
    from scheduler.actions import research_handlers
    task = _red_link(wiki_scheduler.queue, "Epsilon")
    res = asyncio.run(research_handlers.run_batch_action(
        {"managers": {"research_scheduler": wiki_scheduler}, "max_tasks": 1}))
    assert res.success
    _assert_ran_through_runner(task.task_id)


@pytest.mark.xfail(strict=True, reason=(
    "Pre-existing on main: research.run_single and the autonomous_research job's "
    "continuous mode read queue.get_stats()['queued'], but get_stats() returns "
    "'queued_count', so they always see an empty queue and never run a task. "
    "Left as is (fixing it starts research that has not been running); a decision for Kohl."))
@pytest.mark.unit
def test_research_run_single_action_runs_a_task(llm, search_backend, wiki_scheduler):
    from scheduler.actions import research_handlers
    task = _red_link(wiki_scheduler.queue, "Delta")
    asyncio.run(research_handlers.run_single_action({"managers": {"research_scheduler": wiki_scheduler}}))
    _assert_ran_through_runner(task.task_id)


@pytest.mark.unit
def test_question_task_has_no_llm_step(llm, search_backend, wiki_scheduler):
    task = ResearchTask(task_id=create_task_id(), task_type=TaskType.QUESTION,
                        target="Why do tides lag?", context="test", priority=0.9)
    wiki_scheduler.queue.add(task)
    asyncio.run(wiki_scheduler.run_single_task())
    status, result, _p, _t = _row(task.task_id)
    assert status == "completed" and result["models"] == {}  # recorded, and empty: no LLM step
    assert llm.calls == []
    assert search_backend.queries == ["Why do tides lag?"]


@pytest.mark.unit
def test_wiki_batches_never_pick_session_tasks(llm, search_backend, wiki_scheduler):
    runner = get_research_pipeline()
    session_task = runner.enqueue_session(engine="legacy", focus="Mycelium", duration_minutes=10,
                                          trigger="scheduled", priority=1.0)
    assert asyncio.run(wiki_scheduler.run_single_task()) is None
    assert _row(session_task.task_id)[0] == "queued"


# ---------------------------------------------------------------------------
# Session entry points: queued, then run at once on the session runner
# ---------------------------------------------------------------------------

def _assert_session_completed(trigger, engine="legacy", models=None):
    rows = _session_rows()
    assert len(rows) == 1, rows
    status, result, params, task_type = rows[0]
    assert task_type == "session"
    assert status == "completed", (status, result)
    assert params["trigger"] == trigger and params["engine"] == engine
    if models is not None:
        assert result["models"] == models


@pytest.mark.unit
def test_admin_start_route_queues_and_runs_session():
    pytest.importorskip("multipart")  # route modules need the runtime deps
    from routes.autonomous_research import (
        AutonomousResearchStartRequest, init_autonomous_research_routes, start_autonomous_research)
    runner = FakeLegacyRunner()
    init_autonomous_research_routes(lambda: runner)

    async def go():
        out = await start_autonomous_research(
            AutonomousResearchStartRequest(focus="Slime molds", duration_minutes=20), None)
        await _drain()
        return out

    out = asyncio.run(go())
    assert out["status"] == "started" and out["session_id"] == "rs_1"
    assert runner.started[0]["focus"] == "Slime molds" and runner.started[0]["trigger"] == "admin"
    _assert_session_completed("admin", models={"session.legacy": f"anthropic:{HAIKU}"})


@pytest.mark.unit
def test_session_model_override_is_what_the_step_records():
    LLMConfigManager().set("session.legacy", ModelAssignment("anthropic", "claude-sonnet-4-6"))
    runner = FakeLegacyRunner()

    async def go():
        await get_research_pipeline().start_session(runner, focus="Lichen", duration_minutes=5,
                                                    trigger="admin")
        await _drain()

    asyncio.run(go())
    _assert_session_completed("admin", models={"session.legacy": "anthropic:claude-sonnet-4-6"})


@pytest.mark.unit
def test_cass_initiated_research_tool_queues_and_runs_session():
    if not _has("networkx"):
        pytest.skip("handlers package needs runtime deps")
    from handlers.research_session import execute_research_session_tool
    runner = FakeLegacyRunner()

    async def go():
        out = await execute_research_session_tool(
            "initiate_autonomous_research", {"topic": "Bird migration", "duration_minutes": 15},
            session_manager=None, research_runner=runner)
        await _drain()
        return json.loads(out)

    out = asyncio.run(go())
    assert out["success"] and out["session_id"] == "rs_1"
    _assert_session_completed("self_initiated")


@pytest.mark.unit
def test_approved_session_requests_run_only_with_lever(levers, wiki_scheduler):
    """Approved requests never ran before #60 (check_and_trigger_due_sessions
    had no caller). Now the autonomous_research job starts due ones from the
    queue, but only with the research_session_requests lever on."""
    from datetime import datetime, timedelta
    from research_scheduler import ResearchScheduler as SessionRequests
    from scheduler.handlers import autonomous_research_handler
    requests = SessionRequests()
    req = requests.request_session(focus_description="Coral reefs", duration_minutes=20,
                                   preferred_time="09:00", session_type="research")
    schedule_id = req["schedule_id"]
    assert requests.approve_schedule(schedule_id, approved_by="kohl")["success"]
    requests.schedules[schedule_id].next_run = (datetime.now() - timedelta(minutes=1)).isoformat()
    assert [s.schedule_id for s in requests.get_due_schedules()] == [schedule_id]
    runner = FakeLegacyRunner()

    async def tick():
        await autonomous_research_handler(scheduler=wiki_scheduler, mode="supervised",
                                          session_requests=requests, session_runner_getter=lambda: runner)
        await _drain()

    asyncio.run(tick())  # lever off (default): nothing starts
    assert runner.started == [] and _session_rows() == []

    with levers(research_session_requests=True):
        asyncio.run(tick())
    assert len(runner.started) == 1
    assert runner.started[0]["focus"] == "Coral reefs" and runner.started[0]["trigger"] == "scheduled"
    assert requests.schedules[schedule_id].last_session_id == "rs_1"
    _assert_session_completed("scheduled")


@pytest.mark.unit
def test_session_research_action_queues_generic_session(monkeypatch):
    if not _has("anthropic"):
        pytest.skip("scheduler actions need runtime deps")
    from scheduler.actions import ActionResult, session_handlers
    seen = {}

    async def fake_generic(context, session_type, additions=None):
        seen["args"] = (session_type, additions, context.get("focus"))
        return ActionResult(success=True, message="Research session completed", cost_usd=0.01)

    monkeypatch.setattr(session_handlers, "_run_generic_session", fake_generic)
    session_runner = SimpleNamespace(model=HAIKU)
    res = asyncio.run(session_handlers.research_action(
        {"managers": {"session_runner": session_runner}, "focus": "Fungi", "duration_minutes": 10}))
    assert res.success and seen["args"] == ("research", "Research mode: explore", "Fungi")
    _assert_session_completed("action", engine="generic", models={"session.generic": f"anthropic:{HAIKU}"})


@pytest.mark.unit
def test_session_start_failure_marks_task_failed():
    class Busy(FakeLegacyRunner):
        async def start_session(self, **kw):
            raise ValueError("A session is already active")

    with pytest.raises(ValueError):
        asyncio.run(get_research_pipeline().start_session(Busy(), focus="x", duration_minutes=5,
                                                          trigger="admin"))
    status, result, _p, _t = _session_rows()[0]
    assert status == "failed" and "already active" in result["error"]


@pytest.mark.unit
def test_daily_research_summary_leaves_sessions_out(llm, search_backend, wiki_scheduler):
    from datetime import datetime
    llm.queue_text("# Moss\n\nSmall plants.")
    _red_link(wiki_scheduler.queue, "Moss")
    asyncio.run(wiki_scheduler.run_single_task())

    async def go():
        await get_research_pipeline().start_session(FakeLegacyRunner(), focus="Ferns",
                                                    duration_minutes=5, trigger="admin")
        await _drain()

    asyncio.run(go())
    summary = wiki_scheduler.get_daily_research_summary(datetime.now().strftime("%Y-%m-%d"))
    assert [d["target"] for d in summary["task_details"]] == ["Moss"]


# ---------------------------------------------------------------------------
# Search interface
# ---------------------------------------------------------------------------

ALL_KEYS = {"TAVILY_API_KEY": "t", "BRAVE_SEARCH_API_KEY": "b", "SERPER_API_KEY": "s"}


def _names(env, path):
    return [b.name for b in rsearch.configured_backends(env, path=path)]


@pytest.mark.unit
def test_each_path_defaults_to_its_pre_60_backend():
    """No behaviour change on deploy: each path searches what it searched on main."""
    # chat / sessions / ResearchManager: Tavily, nothing else
    assert _names({"TAVILY_API_KEY": "t"}, "session") == ["tavily"]
    assert _names(ALL_KEYS, "session") == ["tavily"]
    assert _names({}, "session") == []
    # wiki queue / PageResearcher: DuckDuckGo even with Tavily configured
    assert _names(ALL_KEYS, "wiki") == ["duckduckgo"]
    assert _names({}, "wiki") == ["duckduckgo"]
    # web.search: Brave, else Serper, else nothing (this box: nothing)
    assert _names(ALL_KEYS, "web_action") == ["brave"]
    assert _names({"SERPER_API_KEY": "s"}, "web_action") == ["serper"]
    assert _names({"TAVILY_API_KEY": "t"}, "web_action") == []


@pytest.mark.unit
def test_search_order_overrides_are_opt_in():
    env = {"TAVILY_API_KEY": "t", "RESEARCH_SEARCH_ORDER_WIKI": "tavily,duckduckgo"}
    assert _names(env, "wiki") == ["tavily", "duckduckgo"]
    assert _names(env, "session") == ["tavily"]  # other paths untouched
    env = {"TAVILY_API_KEY": "t", "RESEARCH_SEARCH_ORDER": "duckduckgo,tavily"}
    assert _names(env, "session") == ["duckduckgo", "tavily"]


@pytest.mark.unit
def test_paths_without_a_backend_keep_their_old_errors(monkeypatch):
    for k in ALL_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("RESEARCH_SEARCH_ORDER", raising=False)
    from scheduler.actions.web_handlers import web_search_action
    res = asyncio.run(web_search_action({"query": "otters"}))
    assert not res.success
    assert res.message == "No search API configured (BRAVE_SEARCH_API_KEY or SERPER_API_KEY)"
    out = asyncio.run(rsearch.web_search("owls", path="session"))
    assert out["error"] == "TAVILY_API_KEY not configured"


@pytest.mark.unit
def test_wiki_callers_use_the_wiki_path(monkeypatch, wiki_scheduler):
    seen = []

    async def fake_search(query, num_results=10, path="session", **opts):
        seen.append(path)
        return SearchResponse(True, "fake", [SearchHit("t", "u", "text")])

    monkeypatch.setattr(rsearch, "search", fake_search)
    from wiki.page_enricher import PageResearcher
    asyncio.run(wiki_scheduler._search_web("x"))
    asyncio.run(PageResearcher.__new__(PageResearcher)._search_web("y"))
    assert seen == ["wiki", "wiki"]


@pytest.mark.unit
def test_search_falls_back_when_primary_fails():
    down, up = FakeSearch("primary", fail=True), FakeSearch("fallback")
    with use_backends([down, up]):
        out = asyncio.run(rsearch.web_search("ravens"))
    assert out["success"] and out["backend"] == "fallback"
    assert down.queries == ["ravens"] and up.queries == ["ravens"]


@pytest.mark.unit
def test_research_manager_search_uses_interface(search_backend):
    pytest.importorskip("bs4")
    from research import ResearchManager
    out = asyncio.run(ResearchManager().web_search("owls", num_results=3))
    assert out["success"] and out["backend"] == "fake"
    assert out["results"][0]["url"] == "https://example.org/a"
    assert search_backend.queries == ["owls"]


@pytest.mark.unit
def test_web_search_action_uses_interface(search_backend):
    from scheduler.actions.web_handlers import web_search_action
    res = asyncio.run(web_search_action({"query": "otters", "limit": 2}))
    assert res.success and res.data["backend"] == "fake"
    assert res.data["results"][0]["description"].startswith("otters")


# ---------------------------------------------------------------------------
# Migration v64
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_v64_migration_adds_params_json_idempotently(tmp_path):
    from database.migrations import _ensure_research_task_params
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute("CREATE TABLE research_tasks (id TEXT PRIMARY KEY, daemon_id TEXT, task_type TEXT, "
                 "target TEXT, created_at TEXT)")
    conn.execute("INSERT INTO research_tasks VALUES ('t1', 'd', 'red_link', 'X', '2026-01-01')")
    _ensure_research_task_params(conn)
    _ensure_research_task_params(conn)  # second run is a no-op
    cols = {r[1] for r in conn.execute("PRAGMA table_info(research_tasks)").fetchall()}
    assert "params_json" in cols
    assert conn.execute("SELECT COUNT(*) FROM research_tasks").fetchone()[0] == 1


@pytest.mark.unit
def test_fresh_schema_has_params_json():
    from database import get_db
    with get_db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(research_tasks)").fetchall()}
    assert "params_json" in cols
