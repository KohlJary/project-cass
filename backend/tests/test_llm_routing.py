"""
Per-subsystem model routing (#64, with #29, #52, #25).

Every LLM call site resolves its model through llm_config and records usage
in the token ledger (token_usage_records.call_site). These tests check that:

* no code outside llm_caller talks to a model client directly (AST scan),
  apart from the listed exceptions;
* every routed call names a call site registered in llm_config.CALL_SITES,
  and every registered call site is used;
* with no override, each call site resolves to the model it ran before
  routing (dreams stay on Sonnet);
* every call site, called through the router with the fake LLM, runs the
  model llm_config resolves and writes one ledger row with its name;
* an Ollama assignment set for a subsystem is used by its next call (the
  Ollama client is mocked; no network);
* the extractor (#29), title/bootstrap (#52) and wiki (#25) cases.
"""
import ast
import asyncio
import importlib.util
import json
import pathlib

import pytest

import llm_caller
import llm_config
from llm_config import CALL_SITES, LLMConfigManager, ModelAssignment

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# The static checks run everywhere; tests that call through the fake LLM need
# the anthropic SDK (CI's fast job doesn't install it; the full job does).
needs_sdk = pytest.mark.skipif(importlib.util.find_spec("anthropic") is None,
                               reason="needs the anthropic SDK (runtime deps)")
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

@pytest.fixture(autouse=True)
def _ollama_env(monkeypatch):
    """A developer .env with OLLAMA_ENABLED=false must not change these tests."""
    monkeypatch.setenv("OLLAMA_ENABLED", "true")


ROUTER_FUNCS = {"call_llm", "call_llm_sync", "create_message", "create_message_sync",
                "ollama_raw", "resolve_model", "plan_message"}

# Direct model calls allowed outside llm_caller.py, by (file, function):
DIRECT_CALL_EXCEPTIONS = {
    # Chat turns: each user's model setting; they record usage in
    # websocket_handlers. Routing them waits on the agent-loop work (#70).
    ("agent_client.py", "send_message"),
    ("agent_client.py", "continue_with_tool_result"),
    ("agent_client.py", "continue_with_tool_results"),
    ("agent_client.py", "_call_ollama"),      # OllamaClient chat
    ("openai_client.py", "_call_openai"),     # OpenAIClient chat
}
# Benchmarks and one-off scripts name their models on purpose (folding them
# into the benchmark suite is a separate task on #64).
EXCEPTION_DIRS = ("tests/", "venv/", "llm_bench/", "scripts/",
                  "music/ace-step/")  # a gitignored local ACE-Step checkout, with its own .venv

LLM_URL_MARKERS = ("api/generate", "api/chat", "api.anthropic.com", "api.openai.com",
                   "/v1/messages", "/v1/chat/completions")


def _chain(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _backend_files():
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith(EXCEPTION_DIRS) or "/venv/" in rel or "/.venv/" in rel:
            continue
        yield rel, path


def _enclosing_functions(tree):
    owner = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                owner[id(child)] = node  # innermost wins (walk is outer-first)
    return owner


def _scan():
    """(direct_calls, routed_calls): direct model calls and router calls in backend code."""
    direct, routed = [], []
    for rel, path in _backend_files():
        src = path.read_text(errors="ignore")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        owner = _enclosing_functions(tree)
        from_router = {a.asname or a.name for n in ast.walk(tree)
                       if isinstance(n, ast.ImportFrom) and n.module in ("llm_caller", "llm_config")
                       for a in n.names}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            chain = _chain(node.func)
            last = chain.split(".")[-1]
            fn = owner.get(id(node))
            fname = fn.name if fn else "<module>"
            kind = None
            if chain.endswith(("messages.create", "messages.stream")):
                kind = "anthropic"
            elif chain.endswith("completions.create"):
                kind = "openai"
            elif last in ("post", "stream") and node.args:
                seg = ast.get_source_segment(src, node.args[0]) or ""
                if any(m in seg for m in LLM_URL_MARKERS):
                    kind = "http"
            if kind:
                direct.append((rel, fname, node.lineno, kind))
            # Only names imported from llm_caller/llm_config count (agent_loop
            # has its own resolve_model).
            if last in ROUTER_FUNCS and rel != "llm_caller.py" and (last in from_router or "." in chain):
                routed.append((rel, fname, node, fn))
            # agent_client.generate(_simple) callers pass call_site= by keyword
            for kw in node.keywords:
                if kw.arg == "call_site" and last in ("generate", "generate_simple"):
                    routed.append((rel, fname, kw.value, fn))
    return direct, routed


def _site_names(routed):
    """Literal call-site names used, and calls whose name isn't a literal."""
    names, unresolved = set(), []
    for rel, fname, node, fn in routed:
        arg = node if not isinstance(node, ast.Call) else (
            node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "call_site"), None))
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            names.add(arg.value)
        elif isinstance(arg, ast.Name) and fn is not None:
            # A `call_site` parameter: take its default value.
            args = fn.args
            params = args.args + args.kwonlyargs
            defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults) + list(args.kw_defaults)
            found = [d for p, d in zip(params, defaults) if p.arg == arg.id]
            if found and isinstance(found[0], ast.Constant):
                names.add(found[0].value)
            else:
                unresolved.append((rel, fname, getattr(node, "lineno", 0)))
        else:
            unresolved.append((rel, fname, getattr(node, "lineno", 0)))
    return names, unresolved


# ---------------------------------------------------------------------------
# Static: every call site goes through llm_caller with a registered name
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_no_direct_model_calls_outside_llm_caller():
    direct, _ = _scan()
    offenders = [(rel, fn, line, kind) for rel, fn, line, kind in direct
                 if rel != "llm_caller.py" and (rel, fn) not in DIRECT_CALL_EXCEPTIONS]
    assert offenders == [], (
        "LLM calls that bypass llm_caller (route them through call_llm/create_message "
        f"with a call site registered in llm_config.CALL_SITES): {offenders}")


@pytest.mark.unit
def test_exceptions_list_is_current():
    direct, _ = _scan()
    seen = {(rel, fn) for rel, fn, _line, _kind in direct}
    assert DIRECT_CALL_EXCEPTIONS <= seen, f"stale exceptions: {DIRECT_CALL_EXCEPTIONS - seen}"


@pytest.mark.unit
def test_routed_calls_name_registered_call_sites():
    _, routed = _scan()
    names, unresolved = _site_names(routed)
    assert unresolved == [], f"router calls whose call site isn't a literal: {unresolved}"
    unknown = names - set(CALL_SITES)
    assert unknown == set(), f"call sites used in code but missing from llm_config.CALL_SITES: {unknown}"
    unused = set(CALL_SITES) - names - {"chat"}
    assert unused == set(), f"registered call sites no code uses: {unused}"


# ---------------------------------------------------------------------------
# Defaults: exactly what each call site ran before routing
# ---------------------------------------------------------------------------

# Static defaults, taken from each call site's code before routing (#64 PR).
PRE_ROUTING_MODELS = {
    "title_generation": ("anthropic", HAIKU),
    "identity_snippet": ("anthropic", HAIKU),
    "reach_out.compose": ("anthropic", HAIKU),
    "narrative.extraction": ("anthropic", HAIKU),
    "grimoire.ask_yes_no": ("anthropic", HAIKU),
    "grimoire.choose": ("anthropic", HAIKU),
    "grimoire.rate": ("anthropic", HAIKU),
    "grimoire.generate": ("anthropic", HAIKU),
    "grimoire.reflect": ("anthropic", HAIKU),
    "per_user_journal": ("anthropic", HAIKU),
    "growth_edge_evaluation": ("anthropic", HAIKU),
    "open_question_reflection": ("anthropic", HAIKU),
    "bootstrap.self_model": ("anthropic", HAIKU),
    "research_journal": ("anthropic", HAIKU),
    "world_awareness_journal": ("anthropic", HAIKU),
    "intention_review": ("anthropic", HAIKU),
    "development_log_entry": ("anthropic", HAIKU),
    "research_session_reflection": ("anthropic", HAIKU),
    "research.integration.observations": ("anthropic", HAIKU),
    "research.integration.opinions": ("anthropic", HAIKU),
    "research.integration.growth": ("anthropic", HAIKU),
    "dreaming.the_dreaming": ("anthropic", SONNET),
    "dreaming.cass_voice": ("anthropic", SONNET),
    "dreaming.insight_extraction": ("anthropic", SONNET),
    "art_choice.choose_subject": ("anthropic", HAIKU),
    "art_choice.see_painting": ("anthropic", HAIKU),
    "art_study.biographical_summary": ("anthropic", HAIKU),
    "art_study.observation_extraction": ("anthropic", HAIKU),
    "art_study.deep_analysis": ("anthropic", SONNET),
    "art_study.artist_synthesis": ("anthropic", SONNET),
    "art_study.house_style_extraction": ("anthropic", HAIKU),
    "art_study.house_style_generation": ("anthropic", SONNET),
    "art_study.creative_session": ("anthropic", SONNET),
    "art_study.house_style_vision": ("anthropic", SONNET),
    "art_study.evaluate_creation": ("anthropic", SONNET),
    "art_study.plan_refinement": ("anthropic", SONNET),
    "wonderland.self_observations": ("anthropic", HAIKU),
}
LOCAL_FIRST = ["memory.journal_entry",
               "self_observation_extraction", "self_observation_extraction.conversation",
               "user_observation_extraction"]
LOCAL_NO_FALLBACK = ["opinion_extraction", "memory.observation_extraction"]
LOCAL_ONLY = ["memory.gist", "memory.journal_summary", "query_constructor"]


@pytest.mark.unit
@pytest.mark.parametrize("site", sorted(PRE_ROUTING_MODELS))
def test_static_default_is_the_pre_routing_model(site):
    a = LLMConfigManager().resolve(site)
    assert (a.provider, a.model_id) == PRE_ROUTING_MODELS[site]
    assert a.fallback_provider is None


@pytest.mark.unit
def test_env_dependent_defaults(monkeypatch):
    import config
    m = LLMConfigManager()
    monkeypatch.setattr(config, "OLLAMA_ENABLED", False)
    for site in LOCAL_FIRST + LOCAL_NO_FALLBACK:
        a = m.resolve(site)
        assert (a.provider, a.model_id, a.fallback_provider) == ("anthropic", HAIKU, None), site
    for site in LOCAL_ONLY:
        assert m.resolve(site) is None, site  # call skipped, as before
    assert m.resolve("memory.summary_readiness").model_id == config.SUMMARIZER_MODEL_HAIKU

    monkeypatch.setattr(config, "OLLAMA_ENABLED", True)
    for site in LOCAL_FIRST:
        a = m.resolve(site)
        assert (a.provider, a.model_id, a.fallback_provider, a.fallback_model_id) == (
            "ollama", config.OLLAMA_MODEL, "anthropic", HAIKU), site
    for site in LOCAL_NO_FALLBACK + LOCAL_ONLY + ["memory.summary_readiness"]:
        a = m.resolve(site)
        assert (a.provider, a.model_id, a.fallback_provider) == ("ollama", config.OLLAMA_MODEL, None), site


@pytest.mark.unit
@pytest.mark.parametrize("provider,ollama,expected", [
    ("haiku", False, ("anthropic", HAIKU, None)),
    ("haiku", True, ("anthropic", HAIKU, None)),
    ("sonnet", False, ("anthropic", SONNET, None)),
    ("ollama", True, ("ollama", "OLLAMA", "anthropic")),
    ("ollama", False, ("anthropic", SONNET, None)),  # old quirk: ollama w/o Ollama ran Sonnet
])
def test_summarizer_default_follows_summarizer_provider(monkeypatch, provider, ollama, expected):
    import config
    monkeypatch.setattr(config, "SUMMARIZER_PROVIDER", provider)
    monkeypatch.setattr(config, "OLLAMA_ENABLED", ollama)
    for site in ("memory.summary_chunk", "memory.working_summary"):
        a = LLMConfigManager().resolve(site)
        model = config.OLLAMA_MODEL if expected[1] == "OLLAMA" else expected[1]
        assert (a.provider, a.model_id, a.fallback_provider) == (expected[0], model, expected[2])


@pytest.mark.unit
def test_caller_default_wins_without_override_and_override_wins_with_one():
    m = LLMConfigManager()
    caller = ModelAssignment("anthropic", "claude-from-caller")
    assert m.resolve("goal_planner.subgoals", caller) == caller
    m.set("goal_planner.subgoals", ModelAssignment("ollama", "qwen2.5:14b"))
    assert m.resolve("goal_planner.subgoals", caller).model_id == "qwen2.5:14b"
    m.clear("goal_planner.subgoals")
    assert m.resolve("goal_planner.subgoals", caller) == caller


@pytest.mark.unit
def test_dreams_and_chat_are_pinned(llm_config_file):
    m = LLMConfigManager()
    for site in ("dreaming.the_dreaming", "dreaming.cass_voice", "dreaming.insight_extraction", "chat"):
        with pytest.raises(llm_config.PinnedCallSite):
            m.set(site, ModelAssignment("ollama", "llama3.1:8b-instruct-q8_0"))
    # Even an override written into the file by hand is ignored for a pinned site.
    llm_config_file.write_text(json.dumps({"version": 2, "assignments": {
        "dreaming.the_dreaming": {"provider": "ollama", "model_id": "x"}}}))
    LLMConfigManager.reset_instance()
    assert LLMConfigManager().resolve("dreaming.the_dreaming").model_id == SONNET


@pytest.mark.unit
def test_format1_file_only_keeps_grimoire_assignments(llm_config_file):
    """Old files stored every assignment, but only Grimoire ever read them."""
    llm_config_file.write_text(json.dumps({"assignments": {
        "grimoire.rate": {"provider": "ollama", "model_id": "qwen2.5:latest"},
        "research_journal": {"provider": "ollama", "model_id": "qwen2.5:latest"},
        "title_generation": {"provider": "ollama", "model_id": "qwen2.5:latest"},
    }}))
    LLMConfigManager.reset_instance()
    m = LLMConfigManager()
    assert m.resolve("grimoire.rate").model_id == "qwen2.5:latest"
    assert m.resolve("research_journal").model_id == HAIKU
    assert m.resolve("title_generation").model_id == HAIKU


@pytest.mark.unit
def test_overrides_persist_in_format2(llm_config_file):
    LLMConfigManager().set("rss.triage", ModelAssignment("anthropic", HAIKU))
    data = json.loads(llm_config_file.read_text())
    assert data["version"] == 2 and list(data["assignments"]) == ["rss.triage"]
    LLMConfigManager.reset_instance()
    assert LLMConfigManager().resolve("rss.triage").model_id == HAIKU


@pytest.mark.unit
def test_unknown_call_site_cannot_be_set():
    with pytest.raises(llm_config.UnknownCallSite):
        LLMConfigManager().set("no.such.site", ModelAssignment("anthropic", HAIKU))


# ---------------------------------------------------------------------------
# Every call site: resolves through llm_config and records usage (fake LLM)
# ---------------------------------------------------------------------------

def _ledger(call_site=None):
    from database import get_db
    with get_db() as conn:
        if call_site is None:
            rows = conn.execute("SELECT call_site, provider, model, input_tokens, output_tokens "
                                "FROM token_usage_records").fetchall()
        else:
            rows = conn.execute("SELECT call_site, provider, model, input_tokens, output_tokens "
                                "FROM token_usage_records WHERE call_site = ?", (call_site,)).fetchall()
    return [tuple(r) for r in rows]


def _caller_default(site):
    """What a from_caller site's code passes; None for registered policies."""
    s = CALL_SITES[site]
    if getattr(s.default, "from_caller", False):
        return s.default() or ModelAssignment("anthropic", HAIKU)
    return None


@pytest.fixture
def ollama_on(monkeypatch):
    import config
    monkeypatch.setattr(config, "OLLAMA_ENABLED", True)


ROUTED_SITES = sorted(set(CALL_SITES) - {"chat"})


@pytest.mark.unit
@needs_sdk
@pytest.mark.parametrize("site", ROUTED_SITES)
def test_each_call_site_resolves_through_llm_config_and_records_usage(site, fake_llm, ollama_on):
    default = _caller_default(site)
    expected = LLMConfigManager().resolve(site, default)
    assert expected is not None, f"{site} resolves to no model"
    fake_llm.queue_text("routed reply", input_tokens=21, output_tokens=8)

    if CALL_SITES[site].text_only:
        resp = asyncio.run(llm_caller.call_llm(site, user_prompt="hello", default=default))
        assert resp.success, resp.error
        assert (resp.provider, resp.model_id) == (expected.provider, expected.model_id)
    else:
        msg = asyncio.run(llm_caller.create_message(
            site, default=default, max_tokens=50, messages=[{"role": "user", "content": "hello"}]))
        assert msg.content[0].text == "routed reply"

    call = fake_llm.calls[-1]
    assert call.model == expected.model_id
    assert call.source.startswith("ollama" if expected.provider == "ollama" else expected.provider)
    rows = _ledger(site)
    assert rows == [(site, expected.provider, expected.model_id, 21, 8)]


@pytest.mark.unit
@needs_sdk
@pytest.mark.parametrize("site", [s for s in ROUTED_SITES
                                  if CALL_SITES[s].text_only and not CALL_SITES[s].pinned])
def test_ollama_assignment_is_used_by_the_next_call(site, fake_llm):
    LLMConfigManager().set(site, ModelAssignment("ollama", "qwen2.5:14b"))
    fake_llm.queue_text("local reply")
    resp = asyncio.run(llm_caller.call_llm(site, user_prompt="hello", default=_caller_default(site)))
    assert resp.success and resp.provider == "ollama"
    assert fake_llm.calls[-1].source == "ollama"
    assert fake_llm.calls[-1].model == "qwen2.5:14b"
    assert _ledger(site) == [(site, "ollama", "qwen2.5:14b", 10, 5)]


@pytest.mark.unit
@needs_sdk
def test_create_message_runs_text_requests_on_an_assigned_ollama_model(fake_llm):
    LLMConfigManager().set("research_journal", ModelAssignment("ollama", "qwen2.5:14b"))
    fake_llm.queue_text("a local journal")
    msg = asyncio.run(llm_caller.create_message(
        "research_journal", max_tokens=100, system="be Cass",
        messages=[{"role": "user", "content": "today"}]))
    assert msg.content[0].text == "a local journal"
    call = fake_llm.calls[-1]
    assert call.source == "ollama" and call.kwargs["endpoint"] == "chat"
    assert call.kwargs["messages"][0] == {"role": "system", "content": "be Cass"}


@pytest.mark.unit
@needs_sdk
def test_tool_requests_stay_on_claude_when_assigned_ollama(fake_llm):
    LLMConfigManager().set("session.generic", ModelAssignment("ollama", "qwen2.5:14b"))
    fake_llm.queue_text("ok")
    asyncio.run(llm_caller.create_message(
        "session.generic", model=HAIKU, max_tokens=50,
        tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}],
        messages=[{"role": "user", "content": "go"}]))
    assert fake_llm.calls[-1].source == "anthropic.async"
    assert fake_llm.calls[-1].model == HAIKU


@pytest.mark.unit
@needs_sdk
def test_fallback_runs_when_primary_fails(fake_llm, monkeypatch):
    LLMConfigManager().set("wiki.enrich_page", ModelAssignment("ollama", "llama3.1:8b", "anthropic", HAIKU))

    async def unreachable(*a, **k):
        import httpx
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm_caller, "_ollama_request", unreachable)
    fake_llm.queue_text("# Page\n\nfrom Claude")
    resp = asyncio.run(llm_caller.call_llm("wiki.enrich_page", user_prompt="x"))
    assert resp.success and resp.provider == "anthropic"
    assert _ledger("wiki.enrich_page") == [("wiki.enrich_page", "anthropic", HAIKU, 10, 5)]


@pytest.mark.unit
@needs_sdk
def test_ollama_enabled_false_turns_ollama_assignments_into_their_fallback(fake_llm, monkeypatch):
    """As the old llm_caller did for Grimoire's stored Ollama assignments."""
    LLMConfigManager().set("grimoire.rate", ModelAssignment("ollama", "mistral:7b", "anthropic", HAIKU))
    monkeypatch.setenv("OLLAMA_ENABLED", "false")
    fake_llm.queue_text('{"rating": 0.5}')
    resp = asyncio.run(llm_caller.call_llm("grimoire.rate", user_prompt="x"))
    assert resp.provider == "anthropic" and fake_llm.calls[-1].source == "anthropic.async"


@pytest.mark.unit
@needs_sdk
def test_skipped_call_writes_nothing(fake_llm, monkeypatch):
    import config
    monkeypatch.setattr(config, "OLLAMA_ENABLED", False)
    resp = asyncio.run(llm_caller.call_llm("memory.gist", user_prompt="x"))
    assert not resp.success and fake_llm.calls == [] and _ledger() == []


# ---------------------------------------------------------------------------
# Real call sites
# ---------------------------------------------------------------------------

@pytest.mark.unit
@needs_sdk
def test_title_generation_records_usage_and_follows_an_ollama_assignment(fake_llm):
    """#52: a title is generated and a token_usage row is written."""
    from summary_generation import generate_conversation_title

    class Conversations:
        titles = {}

        def update_title(self, cid, title):
            self.titles[cid] = title

    convs = Conversations()
    fake_llm.queue_text("Sensor Module Debugging")
    asyncio.run(generate_conversation_title("c1", "hi", "hello", convs))
    assert convs.titles["c1"] == "Sensor Module Debugging"
    assert fake_llm.calls[-1].source == "anthropic.async" and fake_llm.calls[-1].model == HAIKU
    assert _ledger("title_generation") == [("title_generation", "anthropic", HAIKU, 10, 5)]

    # Set it to a local model: the next title uses it.
    LLMConfigManager().set("title_generation", ModelAssignment("ollama", "llama3.2:3b"))
    fake_llm.queue_text("Local Title")
    asyncio.run(generate_conversation_title("c2", "hi", "hello", convs))
    assert convs.titles["c2"] == "Local Title"
    assert fake_llm.calls[-1].source == "ollama" and fake_llm.calls[-1].model == "llama3.2:3b"


@pytest.mark.unit
@needs_sdk
def test_bootstrap_self_model_records_usage(fake_llm):
    """#52: the bootstrap analysis call is recorded."""
    from bootstrap_self_model import analyze_journals_for_self_model
    fake_llm.queue_text("PATTERN | asks questions | 0.8")
    out = asyncio.run(analyze_journals_for_self_model(
        [{"metadata": {"journal_date": "2026-10-01"}, "content": "a day"}], "test-key"))
    assert out.startswith("PATTERN")
    assert _ledger("bootstrap.self_model") == [("bootstrap.self_model", "anthropic", HAIKU, 10, 5)]


@pytest.mark.unit
@needs_sdk
def test_self_observation_extractor_records_one_row_per_claude_call(fake_llm, monkeypatch):
    """#29: the journal self-observation extractor's Claude call is in the ledger."""
    import config
    from memory.self_model import SelfModelMemory
    monkeypatch.setattr(config, "OLLAMA_ENABLED", False)
    fake_llm.queue_text("PATTERN | I ask clarifying questions before diving in | 0.8 | independent")
    mem = SelfModelMemory.__new__(SelfModelMemory)
    obs = asyncio.run(mem.extract_self_observations_from_journal("journal text", "2026-10-01", "test-key"))
    assert [o["category"] for o in obs] == ["pattern"]
    assert _ledger("self_observation_extraction") == [
        ("self_observation_extraction", "anthropic", HAIKU, 10, 5)]


@pytest.mark.unit
@needs_sdk
def test_self_observation_extractor_falls_back_to_claude_when_ollama_finds_nothing(fake_llm, ollama_on):
    from memory.self_model import SelfModelMemory
    fake_llm.queue_text("NONE")
    fake_llm.queue_text("GROWTH | I hold uncertainty longer than I used to | 0.7 | synthesis")
    mem = SelfModelMemory.__new__(SelfModelMemory)
    obs = asyncio.run(mem.extract_self_observations_from_journal("journal text", "2026-10-01", "test-key"))
    assert [o["category"] for o in obs] == ["growth"]
    assert [c.source for c in fake_llm.calls] == ["ollama", "anthropic.async"]
    assert [r[1] for r in _ledger("self_observation_extraction")] == ["ollama", "anthropic"]


@pytest.mark.unit
@needs_sdk
def test_wiki_enrichment_with_ollama_down(fake_llm, monkeypatch):
    """#25: by default wiki stays Ollama-only (and reports the failure); with
    an Anthropic fallback assigned, enrichment returns content and records usage."""
    from wiki.page_enricher import PageEnricher

    async def unreachable(*a, **k):
        import httpx
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm_caller, "_ollama_request", unreachable)

    class Storage:
        updated = {}

        def update(self, name, content):
            self.updated[name] = content

        def read(self, name):
            return None

    class Page:
        name = "Sensor Module"
        page_type = type("T", (), {"value": "concept"})()

    enricher = PageEnricher.__new__(PageEnricher)
    enricher._wiki_storage = Storage()
    enricher._memory = None
    enricher._ollama_url = "http://ollama.invalid:11434"
    enricher._ollama_model = "llama3.1:8b-instruct-q8_0"
    enricher._get_context_snippets = lambda name: []
    enricher._build_enrich_prompt = lambda page, snippets: "write about it"

    result = asyncio.run(enricher.enrich_page(Page()))
    assert result.status == "error" and "connection refused" in (result.error or "")
    assert fake_llm.calls == []

    LLMConfigManager().set("wiki.enrich_page",
                           ModelAssignment("ollama", "llama3.1:8b-instruct-q8_0", "anthropic", HAIKU))
    fake_llm.queue_text("# Sensor Module\n\nWhat I know so far.")
    result = asyncio.run(enricher.enrich_page(Page()))
    assert result.status == "enriched"
    assert "What I know so far." in Storage.updated["Sensor Module"]
    assert _ledger("wiki.enrich_page") == [("wiki.enrich_page", "anthropic", HAIKU, 10, 5)]


@pytest.mark.unit
@needs_sdk
def test_call_site_summary_groups_by_call_site(fake_llm):
    from token_tracker import TokenUsageTracker
    fake_llm.queue_text("a")
    fake_llm.queue_text("b")
    asyncio.run(llm_caller.call_llm("grimoire.rate", user_prompt="x"))
    asyncio.run(llm_caller.call_llm("grimoire.rate", user_prompt="y"))
    TokenUsageTracker().record(category="chat", operation="initial_message",
                               provider="anthropic", model=HAIKU, input_tokens=5, output_tokens=5)
    summary = TokenUsageTracker().get_call_site_summary(days=1)
    assert summary["grimoire.rate"]["calls"] == 2
    assert summary["grimoire.rate"]["input_tokens"] == 20
    assert summary["grimoire.rate"]["cost_usd"] > 0
    assert summary["chat"]["calls"] == 1


# ---------------------------------------------------------------------------
# Ollama down: no paid fallback where there was none before routing
# ---------------------------------------------------------------------------

def _ollama_down(monkeypatch):
    async def unreachable(*a, **k):
        import httpx
        raise httpx.ConnectError("connection refused")

    def unreachable_sync(*a, **k):
        import httpx
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm_caller, "_ollama_request", unreachable)
    monkeypatch.setattr(llm_caller, "_ollama_request_sync", unreachable_sync)


def _ollama_status(monkeypatch, code=500):
    async def failing(*a, **k):
        raise llm_caller.ProviderHTTPError(f"Ollama HTTP {code}: boom")

    monkeypatch.setattr(llm_caller, "_ollama_request", failing)


NO_FALLBACK_ON_EXCEPTION = ["memory.summary_chunk", "memory.working_summary", "memory.journal_entry",
                            "self_observation_extraction", "self_observation_extraction.conversation",
                            "user_observation_extraction"]


@pytest.mark.unit
@needs_sdk
@pytest.mark.parametrize("site", NO_FALLBACK_ON_EXCEPTION)
def test_ollama_exception_makes_no_paid_call_where_main_made_none(site, fake_llm, ollama_on, monkeypatch):
    import config
    monkeypatch.setattr(config, "SUMMARIZER_PROVIDER", "ollama")
    assert LLMConfigManager().resolve(site).fallback_provider == "anthropic"
    _ollama_down(monkeypatch)
    resp = asyncio.run(llm_caller.call_llm(site, user_prompt="x"))
    assert resp.error_kind == "exception" and resp.provider == "ollama"
    assert fake_llm.calls == [] and _ledger() == []


@pytest.mark.unit
@needs_sdk
@pytest.mark.parametrize("site", NO_FALLBACK_ON_EXCEPTION)
def test_ollama_error_status_still_falls_back_as_before(site, fake_llm, ollama_on, monkeypatch):
    import config
    monkeypatch.setattr(config, "SUMMARIZER_PROVIDER", "ollama")
    _ollama_status(monkeypatch)
    fake_llm.queue_text("from Claude")
    resp = asyncio.run(llm_caller.call_llm(site, user_prompt="x"))
    assert resp.provider == "anthropic" and resp.success


@pytest.mark.unit
@needs_sdk
def test_summary_chunk_with_ollama_down_returns_none_without_claude(fake_llm, ollama_on, monkeypatch):
    """main: generate_summary_chunk returned None on an Ollama exception."""
    import config
    from memory.summaries import SummaryManager
    monkeypatch.setattr(config, "SUMMARIZER_PROVIDER", "ollama")
    _ollama_down(monkeypatch)
    mgr = SummaryManager.__new__(SummaryManager)
    out = asyncio.run(mgr.generate_summary_chunk(
        "c1", [{"role": "user", "content": "hi", "timestamp": "t"}], "test-key"))
    assert out is None and fake_llm.calls == []


@pytest.mark.unit
@needs_sdk
def test_user_observations_with_ollama_down_returns_empty_without_claude(fake_llm, ollama_on, monkeypatch):
    """main: generate_user_observations returned [] on an Ollama exception."""
    from memory.self_model import SelfModelMemory
    _ollama_down(monkeypatch)
    mem = SelfModelMemory.__new__(SelfModelMemory)
    out = asyncio.run(mem.generate_user_observations("u1", "Kohl", "User: hi\nCass: hello", "test-key"))
    assert out == [] and fake_llm.calls == []


@pytest.mark.unit
@needs_sdk
def test_admin_override_falls_back_on_any_failure(fake_llm, monkeypatch):
    LLMConfigManager().set("memory.journal_entry",
                           ModelAssignment("ollama", "qwen2.5:14b", "anthropic", HAIKU))
    _ollama_down(monkeypatch)
    fake_llm.queue_text("journal")
    resp = asyncio.run(llm_caller.call_llm("memory.journal_entry", user_prompt="x"))
    assert resp.provider == "anthropic"


@pytest.mark.unit
def test_dream_pin_ignores_the_callers_model():
    m = LLMConfigManager()
    for site in ("dreaming.the_dreaming", "dreaming.cass_voice", "dreaming.insight_extraction"):
        a = m.resolve(site, ModelAssignment("anthropic", "claude-something-else"))
        assert (a.provider, a.model_id) == ("anthropic", SONNET)
    # Pinned sites whose model is the caller's by design keep the caller's.
    caller = ModelAssignment("openai", "gpt-4o")
    assert m.resolve("interviews.dispatch", caller) == caller


# ---------------------------------------------------------------------------
# Failed attempts are recorded (llm_call_failures), not only logged
# ---------------------------------------------------------------------------

from token_tracker import TokenUsageTracker  # noqa: E402

def _failures(call_site=None):
    from database import get_db
    q = "SELECT call_site, provider, model, error_kind, error_type, fell_back FROM llm_call_failures"
    with get_db() as conn:
        rows = (conn.execute(q + " WHERE call_site = ? ORDER BY id", (call_site,)) if call_site
                else conn.execute(q + " ORDER BY id")).fetchall()
    return [tuple(r) for r in rows]


@pytest.mark.unit
@needs_sdk
@pytest.mark.parametrize("site", NO_FALLBACK_ON_EXCEPTION)
def test_lost_ollama_call_is_recorded_as_lost(site, fake_llm, ollama_on, monkeypatch):
    """An Ollama timeout on an identity site used to leave only a log line."""
    import config
    monkeypatch.setattr(config, "SUMMARIZER_PROVIDER", "ollama")
    _ollama_down(monkeypatch)
    resp = asyncio.run(llm_caller.call_llm(site, user_prompt="x"))
    model = resp.model_id
    assert _failures(site) == [(site, "ollama", model, "exception", "ConnectError", 0)]
    summary = TokenUsageTracker().get_failure_summary(days=1)[site]
    assert summary["failures"] == 1 and summary["lost"] == 1
    assert summary["by_type"] == {"ConnectError": 1} and "connection refused" in summary["last_error"]


@pytest.mark.unit
@needs_sdk
def test_failed_attempt_with_a_fallback_is_recorded_as_fell_back(fake_llm, monkeypatch):
    LLMConfigManager().set("wiki.enrich_page", ModelAssignment("ollama", "llama3.1:8b", "anthropic", HAIKU))
    _ollama_down(monkeypatch)
    fake_llm.queue_text("# Page\n\nfrom Claude")
    resp = asyncio.run(llm_caller.call_llm("wiki.enrich_page", user_prompt="x"))
    assert resp.success
    assert _failures() == [("wiki.enrich_page", "ollama", "llama3.1:8b", "exception", "ConnectError", 1)]
    s = TokenUsageTracker().get_failure_summary(days=1)["wiki.enrich_page"]
    assert s["failures"] == 1 and s["lost"] == 0


@pytest.mark.unit
@needs_sdk
def test_error_status_and_rejected_replies_are_recorded(fake_llm, ollama_on, monkeypatch):
    import config
    monkeypatch.setattr(config, "SUMMARIZER_PROVIDER", "ollama")
    _ollama_status(monkeypatch)
    fake_llm.queue_text("nope")
    resp = asyncio.run(llm_caller.call_llm("memory.journal_entry", user_prompt="x",
                                           accept=lambda t: t != "nope"))
    assert not resp.success or resp.rejected
    rows = _failures("memory.journal_entry")
    assert [(r[1], r[3], r[5]) for r in rows] == [("ollama", "http", 1), ("anthropic", "rejected", 0)]
    assert TokenUsageTracker().get_failure_summary(days=1)["memory.journal_entry"]["rejected"] == 1


@pytest.mark.unit
@needs_sdk
def test_success_records_no_failure(fake_llm):
    fake_llm.queue_text("A title")
    asyncio.run(llm_caller.call_llm("title_generation", user_prompt="x"))
    assert _failures() == []


@pytest.mark.unit
def test_usage_view_carries_failures(monkeypatch):
    from routes.admin import llm_routing
    monkeypatch.setattr(llm_routing, "_usage", lambda days: {"memory.journal_entry": {
        "calls": 3, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "last_call": None, "models": []}})
    monkeypatch.setattr(llm_routing, "_failures", lambda days: {"memory.journal_entry": {
        "failures": 2, "lost": 1, "rejected": 0, "by_kind": {"exception": 2}, "by_type": {},
        "last_failure": "t", "last_error": "e", "failed_ms": 10}})
    usage = asyncio.run(llm_routing.get_llm_usage(days=7, admin={}))["usage"]
    site = usage["memory.journal_entry"]
    assert site["failures"]["lost"] == 1
    assert site["failure_rate"] == 0.4  # 2 failed of 5 attempts
