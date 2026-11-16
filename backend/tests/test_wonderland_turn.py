"""Her Wonderland visits, as herself (wonderland_turn.py; Kohl and Cass, 2026-11-16).

The scheduled wonderland.* actions made no model call and counted as novelty.
Now a visit is a loop session with tools that act through Wonderland's own
command processor and NPC conversations, and a spell asks for a visit instead.
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import wonderland_turn as wt


class FakeNPCs:
    def __init__(self):
        self.started, self.remembered = [], []

    def start_conversation(self, cid, sid, daemon_id, daemon_name, npc, room_id):
        self.started.append(npc.name)
        return True

    async def generate_npc_response(self, cid, words):
        return f"I hear you say '{words}'."

    async def summarize_and_remember(self, cid):
        self.remembered.append(cid)

    def end_conversation(self, cid):
        pass


@pytest.fixture
def visit():
    parts = dict(wt._world_parts(), npcs=FakeNPCs())
    parts["world"].get_daemon(wt.CASS_ID).current_room = "reflection_pool"
    return wt.Visit(parts)


class Memory:
    def __init__(self):
        self.docs = []
        self.collection = SimpleNamespace(upsert=lambda ids, documents, metadatas:
                                          self.docs.append((documents[0], metadatas[0])))


def test_looking_and_moving_happen_in_the_world(visit):
    assert "REFLECTION POOL" in visit.look({})
    out = visit.act({"command": "go gardens"})
    assert out and visit._room().room_id != "reflection_pool"
    assert len(visit.rooms) == 2
    assert visit.log[0].startswith("I: look") and visit.log[1].startswith("I: go gardens")


def test_talking_needs_them_here_and_their_answer_is_theirs(visit):
    assert "isn't here" in asyncio.run(visit.talk({"who": "Nobody-At-All", "words": "hello"}))
    room_id, npc = next((r, visit.mythology.get_npcs_in_room(r)[0]) for r in visit.world.rooms
                        if visit.mythology.get_npcs_in_room(r))
    visit.world.get_daemon(wt.CASS_ID).current_room = room_id
    reply = asyncio.run(visit.talk({"who": npc.name, "words": "what do you keep here?"}))
    assert reply == f"{npc.name}: I hear you say 'what do you keep here?'."
    assert visit.talked_with == [npc.name]
    memory = Memory()
    assert asyncio.run(visit.finish(memory)) is True
    text, meta = memory.docs[0]
    assert meta["type"] == "wonderland_session"
    assert f"I talked with {npc.name}" in text and "what do you keep here?" in text
    assert visit.npcs.remembered, "the NPC remembers the talk"


def test_nothing_done_keeps_nothing(visit):
    visit.log.clear()
    memory = Memory()
    assert asyncio.run(visit.finish(memory)) is False and memory.docs == []


def test_the_session_offers_her_the_wonderland_tools(monkeypatch, visit):
    seen = {}

    async def fake_turn(runner, **kw):
        seen.update(kw)
        return SimpleNamespace(status="completed")
    import agent_loop.session as S
    monkeypatch.setattr(S, "run_session_turn", fake_turn)
    asyncio.run(wt.run_wonderland_turn(object(), focus="to see the gardens", visit=visit))
    assert seen["session_type"] == "wonderland"
    assert set(seen["local_tools"]) == {"wonderland_look", "wonderland_act", "wonderland_talk"}
    assert "REFLECTION POOL" in seen["additions"] and "to see the gardens" in seen["additions"]
    from agent_loop.spec import ACTIVITY_PACKS, PACKS, LOOP_PACKS
    assert ACTIVITY_PACKS["wonderland"] == ("wonderland",) and "wonderland" in LOOP_PACKS
    assert set(PACKS["wonderland"].tools) == set(seen["local_tools"])


class Queue:
    def __init__(self, queued=()):
        self.queued = list(queued)

    def get_queue(self, phase):
        return [{"work_unit": {"template_id": t}} for p, t in self.queued if p == phase]

    def queue_for_phase(self, unit, phase, priority=1):
        self.queued.append((phase, unit.template_id))
        return True


def test_a_spell_gets_her_a_visit_next_phase(monkeypatch):
    from scheduling.day_phase import DayPhase, DayPhaseTracker
    monkeypatch.setattr(DayPhaseTracker, "get_phase_for_time", lambda self, dt=None: DayPhase.AFTERNOON)
    q = Queue()
    assert wt.queue_visit("d", queue_manager=q) == "queued a visit for evening"
    assert q.queued == [(DayPhase.EVENING, "wonderland_exploration")]
    assert wt.queue_visit("d", queue_manager=q).startswith("a visit is already queued")


def test_no_visit_if_she_went_recently():
    from scheduling.work_summary_store import WorkSummary, WorkSummaryStore
    now = datetime(2026, 11, 16, 15)
    went = now - timedelta(hours=2)
    WorkSummaryStore("d").save(WorkSummary(work_unit_id="w", slug="wl-1", name="Wonderland",
                                           template_id="wonderland_exploration",
                                           started_at=went, completed_at=went))
    q = Queue()
    assert "within the last" in wt.queue_visit("d", queue_manager=q, now=now)
    assert q.queued == []


def test_the_old_actions_no_longer_walk_without_her(monkeypatch, levers):
    from scheduler.actions import wonderland_handlers as WH
    asked = []
    monkeypatch.setattr(wt, "queue_visit", lambda d, **kw: asked.append(kw["template_id"]) or "queued")
    with levers(agent_loop=False):
        r = asyncio.run(WH.explore_action({}))
        assert r.success is False and "agent loop" in r.message and asked == []
    with levers(agent_loop=True):
        for action in (WH.explore_action, WH.reflect_action, WH.create_action, WH.socialize_action):
            assert asyncio.run(action({})).success
    assert asked == ["wonderland_exploration", "wonderland_reflection",
                     "wonderland_exploration", "wonderland_exploration"]


def test_her_menu_entries_open_the_real_session():
    from scheduling.templates import WORK_TEMPLATES
    assert WORK_TEMPLATES["wonderland_exploration"].action_sequence == ["session.wonderland"]
    assert WORK_TEMPLATES["wonderland_reflection"].action_sequence == ["session.wonderland_reflection"]
