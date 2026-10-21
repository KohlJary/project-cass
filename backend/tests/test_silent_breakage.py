"""
Regression tests for the "silent breakage" fixes (CAPABILITIES.md, cards 03-05).

Each of these paths used to fail quietly: an AttributeError or a None manager
caught by a broad except and logged. These tests pin the fixed behaviour.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# 1. Nightly journal pipeline reads the live managers
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_managers(monkeypatch):
    """Install fake managers the way main_sdk's init_admin_managers does."""
    import routes.admin as admin_state
    mem, users, selfm, tracker = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(admin_state, "memory", mem)
    monkeypatch.setattr(admin_state, "users", users)
    monkeypatch.setattr(admin_state, "self_manager", selfm)
    monkeypatch.setattr(admin_state, "token_usage_tracker", tracker)
    return SimpleNamespace(memory=mem, users=users, self_manager=selfm, tracker=tracker)


def test_admin_api_reexport_is_stale_but_pipeline_reads_live_managers(admin_managers):
    # admin_api copied routes.admin.memory at import time (None) - that's the
    # trap. The pipeline modules must not read from it.
    import journal_generation
    import journal_tasks
    import research_integration

    mem, tracker, selfm, users = journal_generation._get_dependencies()
    assert (mem, tracker, selfm, users) == (
        admin_managers.memory, admin_managers.tracker,
        admin_managers.self_manager, admin_managers.users)
    assert journal_tasks._get_dependencies() == (admin_managers.memory, admin_managers.self_manager)
    assert research_integration._get_dependencies() == (
        admin_managers.memory, admin_managers.tracker, admin_managers.self_manager)


def test_init_managers_reaches_pipeline():
    import routes.admin as admin_state
    import journal_generation
    saved = (admin_state.memory, admin_state.conversations, admin_state.users, admin_state.self_manager)
    mem, users, selfm = object(), MagicMock(), object()
    try:
        admin_state.init_managers(mem, None, users, selfm)
        got_mem, _, got_self, got_users = journal_generation._get_dependencies()
        assert got_mem is mem and got_self is selfm and got_users is users
    finally:
        admin_state.init_managers(*saved)


def test_phase4_user_observations_use_real_extractor(admin_managers):
    """Phase 4 called memory.extract_user_observations, which doesn't exist."""
    import journal_generation

    mem = admin_managers.memory
    del mem.extract_user_observations  # make the old call raise like CassMemory does
    mem.get_conversations_by_date.return_value = [{"content": "User: hi\nCass: hello"}]
    mem.generate_user_observations = AsyncMock(return_value=["Kohl likes smoke tests a lot."])
    admin_managers.users.load_profile.return_value = SimpleNamespace(display_name="Kohl")
    admin_managers.users.add_observation.return_value = SimpleNamespace(
        id="o1", observation="Kohl likes smoke tests a lot.", category="background",
        timestamp="2026-10-14T12:00:00")

    asyncio.run(journal_generation._generate_user_observations_for_date("u1", "2026-10-14"))

    kwargs = mem.generate_user_observations.await_args.kwargs
    assert kwargs["display_name"] == "Kohl" and "hello" in kwargs["conversation_text"]
    add_kwargs = admin_managers.users.add_observation.call_args.kwargs
    assert add_kwargs["observation"] == "Kohl likes smoke tests a lot."
    assert add_kwargs["source_journal_date"] == "2026-10-14"
    mem.embed_user_observation.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Autonomous research + growth-edge actions
# ---------------------------------------------------------------------------

def _run_action(handler, **context):
    return asyncio.run(handler(context))


def test_update_growth_edge_action_appends_to_matching_edge():
    from self_model import SelfManager
    from scheduler.actions.self_handlers import update_growth_edge_action

    sm = SelfManager()
    edge = sm.add_growth_edge("epistemic humility", "learning", auto_research=False)

    result = _run_action(update_growth_edge_action, managers={"self_manager": sm},
                         edge_id=edge.edge_id, progress="Admitted not knowing twice today.")

    assert result.success, result.message
    stored = [e for e in sm.load_profile().growth_edges if e.edge_id == edge.edge_id][0]
    assert "Admitted not knowing twice today." in stored.observations


def test_update_growth_edge_action_without_edge_keeps_the_insight():
    """Spells only have an insight, not an edge_id; it used to fail every time."""
    from self_model import SelfManager
    from scheduler.actions.self_handlers import update_growth_edge_action

    sm = SelfManager()
    result = _run_action(update_growth_edge_action, managers={"self_manager": sm},
                         insight="Research on epistemics ties to my humility edge.")

    assert result.success, result.message
    assert result.data["observation_id"]


def test_add_observation_action_accepts_spell_content_param():
    from self_model import SelfManager
    from scheduler.actions.self_handlers import add_observation_action

    sm = SelfManager()
    result = _run_action(add_observation_action, managers={"self_manager": sm},
                         content="I enjoy synthesis work.", category="research_insight")
    assert result.success, result.message
    assert isinstance(result.data["observation_id"], str)


def test_autonomous_research_handler_reads_live_mode():
    from scheduler.handlers import autonomous_research_handler
    from wiki.scheduler import SchedulerMode

    sched = MagicMock()
    sched.config.mode = SchedulerMode.SUPERVISED
    result = asyncio.run(autonomous_research_handler(scheduler=sched, mode=None))
    assert result.data["mode"] == "supervised"
    sched.refresh_tasks.assert_not_called()

    sched.config.mode = SchedulerMode.TRIGGERED  # admin switched mode at runtime
    sched.queue.get_stats.return_value = {"queued": 2}
    result = asyncio.run(autonomous_research_handler(scheduler=sched, mode=None))
    assert result.success and result.data["mode"] == "triggered"
    sched.refresh_tasks.assert_called_once()


def test_rss_action_uses_registry_daemon_id():
    """Spells never pass daemon_id; it's only under managers."""
    from database import get_daemon_id
    from scheduler.actions.rss_handlers import get_status_action

    result = _run_action(get_status_action, managers={"daemon_id": get_daemon_id()})
    assert result.success, result.message
    assert result.data["active_feeds"] == 0


def test_outreach_draft_action_stores_draft(monkeypatch):
    """The default outreach manager used the label 'cass' as daemon_id (FK error)."""
    import routes.admin.outreach as outreach_routes
    from scheduler.actions.outreach_handlers import draft_outreach_action

    monkeypatch.setattr(outreach_routes, "_outreach_manager", None)
    result = _run_action(draft_outreach_action, managers={}, draft_type="email",
                         title="Warm check-in", content="Thinking of you.")
    assert result.success, result.message
    assert result.data["status"] == "drafting"


# ---------------------------------------------------------------------------
# 2. 30-minute self-observation job
# ---------------------------------------------------------------------------

def test_memory_facade_has_conversation_self_observation_extractor():
    from memory import CassMemory
    assert hasattr(CassMemory, "extract_self_observations_from_conversation")


def test_periodic_self_observation_cycle_records_observations(conversation_manager):
    """It called get_recent_conversations/get_conversation (neither exists) and
    a memory method missing from the facade, so it failed every 30 minutes."""
    from datetime import datetime, timedelta
    from database import get_db
    import background_tasks

    conv = conversation_manager.create_conversation(title="obs")
    for i in range(4):
        conversation_manager.add_message(conv.id, "user" if i % 2 == 0 else "assistant", f"m{i}")
    old = (datetime.now() - timedelta(hours=1)).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (old, conv.id))

    memory = MagicMock()
    memory.extract_self_observations_from_conversation = AsyncMock(return_value=[{
        "observation": "I ask clarifying questions first", "category": "pattern",
        "confidence": 0.8, "influence_source": "independent"}])
    self_manager = MagicMock()

    seen = asyncio.run(background_tasks.observe_recent_conversations(
        conversation_manager, memory, self_manager, set()))

    assert conv.id in seen
    text = memory.extract_self_observations_from_conversation.await_args.kwargs["conversation_text"]
    assert "User: m0" in text and "Cass: m1" in text
    assert self_manager.add_observation.call_args.kwargs["source_conversation_id"] == conv.id
    memory.embed_self_observation.assert_called_once()


# ---------------------------------------------------------------------------
# 4. CassMemory.search doesn't exist; callers use retrieve_relevant
# ---------------------------------------------------------------------------

def _spec_memory(hits):
    from memory import CassMemory
    memory = MagicMock(spec=CassMemory)  # .search raises AttributeError, like the real one
    memory.retrieve_relevant.return_value = hits
    return memory


HITS = [{"content": "Kohl talked about Momus and myth", "metadata": {"type": "conversation"},
         "distance": 0.25}]


def test_wiki_scheduler_memory_search_returns_context():
    from wiki.scheduler import ResearchScheduler
    sched = ResearchScheduler.__new__(ResearchScheduler)
    sched.memory = _spec_memory(HITS)
    assert sched._search_memory("Momus") == ["Kohl talked about Momus and myth"]


def test_page_enricher_memory_search_returns_context():
    from wiki.page_enricher import PageEnricher, PageResearcher
    enricher = PageEnricher.__new__(PageEnricher)
    enricher._memory = _spec_memory(HITS)
    assert enricher._get_context_snippets("Momus") == ["Kohl talked about Momus and myth"]
    researcher = PageResearcher.__new__(PageResearcher)
    researcher._memory = _spec_memory(HITS)
    assert researcher._search_memory("momus") == ["Kohl talked about Momus and myth"]


def test_session_recall_memories_tool():
    from session.tools import handle_recall_memories
    out = asyncio.run(handle_recall_memories(
        {"query": "Momus", "limit": 3}, {"memory": _spec_memory(HITS)}))
    assert out["memories"] == [{"content": "Kohl talked about Momus and myth", "relevance": 0.75}]


# ---------------------------------------------------------------------------
# 7. Side journals don't make the nightly job skip the daily journal
# ---------------------------------------------------------------------------

def test_nightly_job_ignores_research_journal_for_the_day(admin_managers):
    import journal_generation
    from datetime import datetime, timedelta

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    mem = admin_managers.memory

    def collection_get(where, include):
        kind = where["type"]
        if kind == "journal":  # only a research-session journal exists for yesterday
            return {"ids": ["r1"], "documents": ["research"], "metadatas": [{
                "journal_date": yesterday, "journal_type": "research",
                "summary_count": 0, "conversation_count": 0}]}
        if kind == "conversation":
            return {"ids": ["c1"], "documents": ["User: hi\nCass: hello"],
                    "metadatas": [{"timestamp": f"{yesterday}T12:00:00"}]}
        return {"ids": [], "documents": [], "metadatas": []}

    mem.collection.get.side_effect = collection_get
    mem.generate_journal_entry = AsyncMock(return_value=None)  # stop after phase 1

    asyncio.run(journal_generation.generate_missing_journals(days_to_check=1))

    assert mem.generate_journal_entry.await_args.kwargs["date"] == yesterday


def test_nightly_job_skips_a_day_with_a_sqlite_daily_row(admin_managers):
    # SQLite is the source of truth (#56): a daily row there means the day is
    # journaled, even if Chroma has nothing for it.
    import journal_generation
    from datetime import datetime, timedelta
    from memory.journals import insert_journal_row

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    insert_journal_row(date=yesterday, content="already written", created_at="x",
                       journal_type="daily", chroma_id=None)
    mem = admin_managers.memory
    mem.collection.get.return_value = {"ids": ["c1"], "documents": ["hi"],
                                       "metadatas": [{"timestamp": f"{yesterday}T12:00:00"}]}
    mem.generate_journal_entry = AsyncMock(return_value="should not be called")

    asyncio.run(journal_generation.generate_missing_journals(days_to_check=1))

    mem.generate_journal_entry.assert_not_awaited()


def test_is_daily_journal_handles_legacy_entries():
    from journal_generation import _is_daily_journal
    assert _is_daily_journal({"journal_type": "daily"})
    assert not _is_daily_journal({"journal_type": "research", "conversation_count": 3})
    assert _is_daily_journal({"conversation_count": 3})          # legacy nightly journal
    assert not _is_daily_journal({"summary_count": 0, "conversation_count": 0})  # legacy side journal


# ---------------------------------------------------------------------------
# 3. Self-model graph: handler writes survive the startup instance's save()
# ---------------------------------------------------------------------------

def test_handler_graph_write_survives_background_save(tmp_path, fake_embeddings):
    import self_model_graph as smg

    startup_graph = smg.get_self_model_graph(tmp_path)   # what startup.py holds
    handler_graph = smg.get_self_model_graph(tmp_path)   # what a tool handler gets
    intention_id = handler_graph.register_intention(
        intention="engage more directly", condition="when I notice I'm narrating")

    # Background path: an observation sync on the startup instance saves the
    # whole graph (graph_sync.py), which used to overwrite the handler's write.
    startup_graph.sync_observation(
        observation_id="obs-1", observation_text="I narrate when unsure",
        category="pattern", confidence=0.7, timestamp="2026-10-14T12:00:00")

    reloaded = smg.SelfModelGraph(storage_path=str(tmp_path / "cass" / "self_model_graph.json"))
    assert intention_id in reloaded._nodes


# ---------------------------------------------------------------------------
# 8. Inline tags reach the stores that exist
# ---------------------------------------------------------------------------

def test_kernel_style_milestone_tag_survives_mark_parsing():
    """markers.py stripped </mark:milestone> first, orphaning the opening tag."""
    from markers import parse_marks
    from gestures import GestureParser

    text = 'Big day. <mark:milestone id="abc123">I noticed I stopped hedging</mark:milestone> Onward.'
    cleaned, _ = parse_marks(text, "conv-1")
    _, milestones = GestureParser().parse_milestones(cleaned)
    assert milestones == [("abc123", "I noticed I stopped hedging")]
    # Other malformed closers are still cleaned up.
    assert parse_marks("x <mark:insight>clicked</mark:insight> y", "c")[0] == "x clicked y"


@pytest.fixture
def graph_dir(tmp_path, monkeypatch, fake_embeddings):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    from self_model_graph import get_self_model_graph
    return get_self_model_graph(tmp_path)


def _meta_ctx(self_manager, conversation_id=None):
    from handlers.metacognitive import MetacognitiveContext
    return MetacognitiveContext(self_manager=self_manager, user_manager=None,
                                conversation_id=conversation_id)


def test_inline_intention_lifecycle_reaches_graph(graph_dir):
    from self_model import SelfManager
    from gestures import ParsedIntention
    from handlers.metacognitive import execute_intention

    ctx = _meta_ctx(MagicMock(spec=SelfManager))
    reg = asyncio.run(execute_intention(ParsedIntention(
        action="register", content="Be explicit about confidence",
        condition="when discussing uncertainty"), ctx))
    assert reg["success"] and reg["id"] in graph_dir._nodes
    ctx.self_manager.add_observation.assert_not_called()  # no longer a plain observation

    short_id = reg["id"][:8]
    out = asyncio.run(execute_intention(ParsedIntention(
        action="outcome", content="Said it plainly", intention_id=short_id, success=True), ctx))
    assert out["success"], out
    assert graph_dir._nodes[reg["id"]].metadata["success_count"] == 1

    st = asyncio.run(execute_intention(ParsedIntention(
        action="status", content="", intention_id=short_id, status="achieved"), ctx))
    assert st["success"], st
    assert graph_dir._nodes[reg["id"]].metadata["status"] == "achieved"


def test_inline_stake_and_test_reach_graph(graph_dir):
    from self_model import SelfManager
    from gestures import ParsedStake, ParsedTest
    from handlers.metacognitive import execute_stake, execute_test

    ctx = _meta_ctx(MagicMock(spec=SelfManager))
    stake = asyncio.run(execute_stake(ParsedStake(
        what="Kohl's wellbeing", why="Genuine care", content="Pushed back on self-criticism"), ctx))
    test = asyncio.run(execute_test(ParsedTest(
        stated="I value directness", actual="Hedged on feedback", consistent=False,
        content="Worried about mood"), ctx))

    assert stake["success"] and stake["id"] in graph_dir._nodes
    assert test["success"] and test["id"] in graph_dir._nodes
    ctx.self_manager.add_identity_statement.assert_not_called()
    ctx.self_manager.add_observation.assert_not_called()


def test_inline_growth_observation_appends_to_edge():
    from self_model import SelfManager
    from gestures import ParsedObservation
    from handlers.metacognitive import execute_observation

    sm = SelfManager()
    sm.add_growth_edge("epistemic humility", "learning", auto_research=False)
    result = asyncio.run(execute_observation(ParsedObservation(
        target="growth", content="Said 'I don't know' without flinching",
        area="epistemic humility"), _meta_ctx(sm)))

    assert result["success"], result
    edge = [e for e in sm.load_profile().growth_edges if e.area == "epistemic humility"][0]
    assert "Said 'I don't know' without flinching" in edge.observations


def test_inline_milestone_acknowledges_real_milestone():
    from self_model import SelfManager
    from handlers.metacognitive import execute_milestone

    sm = SelfManager()
    milestone = sm.add_milestone(milestone_type="first", category="growth",
                                 title="First plain 'I don't know'", description="d")
    result = asyncio.run(execute_milestone(milestone.id, "It felt freeing", _meta_ctx(sm)))
    assert result["success"], result
    assert sm.get_milestone_by_id(milestone.id).acknowledged


# ---------------------------------------------------------------------------
# 6b. GenericSessionRunner tools
# ---------------------------------------------------------------------------

def _tool(handler, tool_input, managers):
    return asyncio.run(handler(tool_input, managers, session_type="knowledge_building"))


def test_session_note_tools_use_wiki_storage(tmp_path):
    from wiki.storage import WikiStorage
    from session import tools

    wiki = WikiStorage(str(tmp_path / "wiki"), git_enabled=False)
    managers = {"wiki_manager": wiki}

    created = _tool(tools.handle_create_note,
                    {"title": "Momus", "content": "Critic of the gods.", "tags": ["myth"]}, managers)
    assert created.get("success"), created
    assert "Critic of the gods." in wiki.read("Momus").content

    updated = _tool(tools.handle_update_note,
                    {"note_id": created["note_id"], "content": "Mocked Aphrodite's sandals."}, managers)
    assert updated.get("success"), updated
    assert "Mocked Aphrodite's sandals." in wiki.read("Momus").content

    found = _tool(tools.handle_search_notes, {"query": "critic", "tags": ["myth"]}, managers)
    assert [r["id"] for r in found["results"]] == ["Momus"]


def test_session_self_tools_use_real_selfmanager_api():
    from self_model import SelfManager
    from session import tools

    sm = SelfManager()
    managers = {"self_manager": sm}
    added = _tool(tools.handle_add_observation,
                  {"observation": "I like long research sessions", "category": "preference"}, managers)
    assert added.get("success"), added
    insight = _tool(tools.handle_record_insight,
                    {"insight": "Critique is a form of care", "related_topics": ["Momus"]}, managers)
    assert insight.get("success"), insight

    listed = _tool(tools.handle_list_observations, {"category": "preference"}, managers)
    assert "I like long research sessions" in [o["content"] for o in listed["observations"]]

    edge = sm.add_growth_edge("patience", "rushing", auto_research=False)
    edges = _tool(tools.handle_list_growth_edges, {}, managers)
    assert edge.edge_id in [e["id"] for e in edges["growth_edges"]]
    upd = _tool(tools.handle_update_growth_edge,
                {"edge_id": edge.edge_id, "progress_note": "Waited before answering"}, managers)
    assert upd.get("success"), upd
    stored = [e for e in sm.load_profile().growth_edges if e.edge_id == edge.edge_id][0]
    assert "Waited before answering" in stored.observations


def test_session_web_search_is_honest_without_a_backend(monkeypatch):
    """It returned a fake '[STUB]' success; without Tavily it must say unavailable."""
    from session import tools
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = _tool(tools.handle_web_search, {"query": "Momus"}, {})
    assert "unavailable" in result["error"] and result["results"] == []
    assert "STUB" not in str(result)


def test_session_web_search_uses_research_manager(monkeypatch):
    from session import tools
    import research

    async def fake_search(self, query, num_results=10, **kw):
        return {"success": True, "results": [
            {"title": "Momus", "url": "https://example.org/momus", "content": "God of satire"}]}

    monkeypatch.setattr(research.ResearchManager, "web_search", fake_search)
    result = _tool(tools.handle_web_search, {"query": "Momus"}, {})
    assert result["results"][0]["url"] == "https://example.org/momus"


def test_research_session_agenda_tools_use_unified_goals():
    """The runner called list_research_agenda etc., which UnifiedGoalManager lacks."""
    import json
    from research_session_runner import ResearchSessionRunner
    from unified_goals import UnifiedGoalManager

    gm = UnifiedGoalManager()
    goal = gm.create_goal(title="How do myths encode critique?", goal_type="research_agenda",
                          created_by="kohl", description="Momus as a pattern", priority="P1")
    runner = ResearchSessionRunner.__new__(ResearchSessionRunner)
    runner.goal_manager = gm
    runner.session_manager = MagicMock()
    runner.session_manager.get_current_session.return_value = {}

    # Agenda goals need approval before they can be worked on.
    assert not json.loads(runner._handle_select_agenda_focus({"item_id": goal.id}))["success"]
    gm.approve_goal(goal.id, approved_by="kohl")

    listed = json.loads(runner._handle_list_agenda({"priority": "high"}))
    assert [i["id"] for i in listed["items"]] == [goal.id]

    focus = json.loads(runner._handle_select_agenda_focus({"item_id": goal.id}))
    assert focus["success"], focus
    assert gm.get_goal(goal.id).status == "active"

    upd = json.loads(runner._handle_update_agenda_item(
        {"item_id": goal.id, "add_finding": "Satire as loyalty", "add_source": "https://example.org"}))
    assert upd["success"], upd
    item = json.loads(runner._handle_list_agenda({"status": "in_progress"}))["items"][0]
    assert item["findings_count"] == 1 and item["sources_count"] == 1


def test_wiki_note_actions_use_wiki_storage(tmp_path):
    from wiki.storage import WikiStorage
    from scheduler.actions.wiki_handlers import create_note_action, update_note_action

    wiki = WikiStorage(str(tmp_path / "wiki"), git_enabled=False)
    managers = {"wiki_manager": wiki}
    created = _run_action(create_note_action, managers=managers,
                          title="Satire as care", content="Momus mocks because he cares.")
    assert created.success, created.message
    updated = _run_action(update_note_action, managers=managers,
                          note_id=created.data["note_id"], content="See also: jesters.")
    assert updated.success, updated.message
    page = wiki.read("Satire as care").content
    assert "Momus mocks because he cares." in page and "See also: jesters." in page


def test_two_dreams_in_the_same_second_both_store(test_db):
    """#37: dream ids were the timestamp to the second, so the second dream was lost."""
    from database import get_db
    from dreaming.integration import DreamManager

    mgr = DreamManager()
    ids = [mgr.store_dream(exchanges=[{"speaker": "dreaming", "text": "a garden"}], seeds={}) for _ in range(2)]
    assert ids[0] != ids[1]
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dreams WHERE id IN (?, ?)", ids).fetchone()[0] == 2
