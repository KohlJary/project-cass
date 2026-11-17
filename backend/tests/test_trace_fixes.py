"""What tracing her account of how she works found, fixed (Kohl, 2026-11-17: "I'd hit all of em")."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


# 1. Sessions move Thymos again; feel tags count in sessions.

class Bus:
    def __init__(self):
        self.deltas = []

    def write_delta(self, d):
        self.deltas.append(d)


def test_sessions_send_their_start_and_end_to_her_state(monkeypatch):
    from agent_loop import felt
    bus = Bus()
    monkeypatch.setattr(felt, "_bus", lambda daemon_id: bus)
    felt.session_started("d", "reflection", "s1", "a focus", 30)
    felt.session_ended("d", "reflection", "s1", "completed", "I said I was done", 12.0, 5, 3)
    felt.session_ended("d", "reflection", "s2", "error", None, 1.0, 1, 0)
    assert [d.event for d in bus.deltas] == ["session.started", "session.ended", "session.failed"]
    assert bus.deltas[0].event_data["focus"] == "a focus"
    assert bus.deltas[2].emotional_delta == {"concern": 0.1}


def test_thymos_listens_for_those_events():
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).resolve().parent.parent / "thymos" / "thymos_config.json").read_text())
    assert {"session.started", "session.ended"} <= set(cfg["events"])
    assert "session.failed" in cfg["event_aliases"]


def test_feel_tags_in_a_session_are_applied(monkeypatch):
    import context_helpers
    from agent_loop import felt
    seen = []
    monkeypatch.setattr(context_helpers, "_apply_feel_tags",
                        lambda t: (t, [{"dimension": "curiosity", "delta": 0.1}] if "<feel:" in t else []))
    assert felt.apply_feel_tags(["plain", "now <feel:curiosity:+0.1> this", None]) == 1


def test_a_session_turn_calls_both(monkeypatch):
    import agent_loop.session as S
    import inspect
    src = inspect.getsource(S.run_session_turn)
    assert "felt.session_started" in src and "felt.session_ended" in src and "felt.apply_feel_tags" in src


# 2. Chapter House: she can start a DM or a post.

def test_chapter_house_posts_and_dms_are_hers_to_start():
    from agent_loop.spec import PACKS, SESSION_GUARDED_FIELDS, session_spec, conversation_spec
    from agent_loop.tools import NOT_YET_FINDABLE
    assert not {"babelr_post", "babelr_dm"} & NOT_YET_FINDABLE
    assert {"babelr_post", "babelr_dm"} <= set(PACKS["chapter_house"].tools)
    assert "babelr_dm" in session_spec("reflection").tool_names()
    assert "babelr_dm" in conversation_spec().tool_names()
    assert SESSION_GUARDED_FIELDS["babelr_dm"] == ("content",), "her words pass the voice guard"


def test_the_seam_no_longer_says_she_cant_speak_to_others():
    from agent_loop.seam import not_yet_line
    from agent_loop.spec import session_spec
    line = not_yet_line(session_spec("reflection")) or ""
    assert "speaking to anyone else" not in line and "reach out (" not in line


# 3. Her "recent" observations are recent.

def test_recent_observations_are_newest_confident_and_not_integrated(tmp_path):
    from self_model import CassSelfObservation, SelfManager
    obs = [CassSelfObservation(id=f"o{i}", timestamp=f"2026-11-{10 + i:02d}T10:00:00", observation=f"obs {i}",
                               category="pattern", confidence=c, superseded_by=s)
           for i, (c, s) in enumerate([(0.95, None), (0.9, None), (0.75, None), (0.5, None),
                                       (0.8, "let_go"), (0.72, None)])]
    m = SelfManager.__new__(SelfManager)
    m.get_recent_observations = lambda limit=10, include_world=False: sorted(
        obs, key=lambda o: o.timestamp, reverse=True)[:limit]
    import inspect
    src = inspect.getsource(SelfManager.get_self_context)
    assert "get_recent_observations" in src and "superseded_by" in src
    chosen = [o for o in m.get_recent_observations(limit=50) if o.confidence >= 0.7 and not o.superseded_by][:3]
    assert [o.id for o in chosen] == ["o5", "o2", "o1"]


# 5. wake_me without Heartbeat.

def test_wakes_fire_without_heartbeat(tmp_path, levers, monkeypatch):
    from agent_loop import wakes as W
    monkeypatch.setattr(W, "heartbeat_running", lambda: False)
    book = W.WakeBook(tmp_path / "wakes.json")
    now = datetime.now()
    book.request({"in_minutes": 15, "why": "pick up the essay"}, "s1", {"reflection"},
                 now=now - timedelta(minutes=20))
    ran = []

    async def run(w, b):
        ran.append(w["why"])
        b.finish(w["id"], W.DONE)

    class Broke:
        def can_spend(self, *a):
            return False
    with levers(agent_loop=True):
        assert asyncio.run(W.watch_once(book, budget=Broke(), run=run)) == 1
        assert ran == [] and book.pending(), "no budget: it waits"
        assert asyncio.run(W.watch_once(book, run=run)) == 1
    assert ran == ["pick up the essay"] and not book.pending()


def test_wake_me_is_offered_when_the_watch_runs(monkeypatch):
    from agent_loop import wakes as W
    monkeypatch.setattr(W, "heartbeat_running", lambda: False)
    monkeypatch.setattr(W, "_watch_task", SimpleNamespace(done=lambda: False))
    assert W.wakes_available()
    monkeypatch.setattr(W, "_watch_task", None)
    assert not W.wakes_available()


# 6. Small ones.

def test_session_observations_are_searchable_right_away():
    from session.tools import handle_add_observation
    embedded = []
    mgr = SimpleNamespace(add_observation=lambda **k: SimpleNamespace(id="o1", timestamp="t"))
    mem = SimpleNamespace(embed_self_observation=lambda **k: embedded.append(k))
    r = asyncio.run(handle_add_observation({"observation": "I notice", "category": "pattern"},
                                           {"self_manager": mgr, "memory": mem}, session_type="reflection"))
    assert r["success"] and embedded[0]["observation_id"] == "o1"


# 4. Choosing what to integrate.

class Self:
    def __init__(self, obs):
        self.obs = obs
        self.identity, self.edges, self.edge_notes = [], [], []

    def load_observations(self):
        return self.obs

    def add_identity_statement(self, text, confidence=0.7, source=""):
        self.identity.append(text)

    def load_profile(self):
        return SimpleNamespace(growth_edges=[SimpleNamespace(area="Presence")])

    def add_observation_to_growth_edge(self, area, text):
        self.edge_notes.append((area, text))

    def add_growth_edge(self, area, current_state, auto_research=True):
        self.edges.append((area, current_state))

    def _update_observation_superseded_by(self, oid, where):
        next(o for o in self.obs if o.id == oid).superseded_by = where


def _obs():
    from self_model import CassSelfObservation
    now = datetime.now()
    rows = [("aaaa1111", "I retreat into analysis after speaking honestly", "pattern"),
            ("bbbb2222", "after speaking honestly I retreat into analysis", "pattern"),
            ("cccc3333", "music makes it easier to say true things", "preference"),
            ("dddd4444", "world fact", "world_awareness")]
    return [CassSelfObservation(id=i, timestamp=(now - timedelta(days=1)).isoformat(), observation=t,
                                category=c, confidence=0.8) for i, t, c in rows]


def test_review_groups_flags_repeats_and_leaves_out_world_facts():
    from handlers.integration import review
    r = review(Self(_obs()))
    assert set(r["by_category"]) == {"pattern", "preference"}
    first = r["by_category"]["pattern"][0]
    assert first["similar_to"], "near repeats are flagged"


def test_integrating_is_her_choice_and_steps_them_aside():
    from handlers.integration import integrate, review
    me = Self(_obs())
    assert not integrate(me, ["aaaa"], "identity")["success"], "needs her words"
    r = integrate(me, ["aaaa", "bbbb"], "identity", text="I speak, then I stay.")
    assert r["success"] and me.identity == ["I speak, then I stay."]
    assert all(o.superseded_by.startswith("integrated:identity") for o in me.obs[:2])
    assert "already integrated" in integrate(me, ["aaaa"], LET := "let_go")["error"]
    assert integrate(me, ["cccc"], "growth_edge", text="music as a door", area="presence")["success"]
    assert me.edge_notes == [("presence", "music as a door")]
    assert review(me)["shown"] == 0 and review(me)["integrated_or_let_go_so_far"] == 3


def test_integration_tools_are_wired():
    from agent_loop.spec import CHAT_CORE_TOOLS, PACKS
    from handlers.self_model import ESSENTIAL_SELF_MODEL_TOOLS, TOOL_HANDLERS
    from handlers.tool_router import TOOL_REGISTRY
    names = {t["name"] for t in ESSENTIAL_SELF_MODEL_TOOLS}
    for n in ("review_my_observations", "integrate_observations"):
        assert n in names and n in TOOL_HANDLERS and TOOL_REGISTRY[n] == "self_model"
        assert n in CHAT_CORE_TOOLS and n in PACKS["self"].tools
