"""Her day plan moves her plans and fills her day (2026-11-17): items can have a
time and carry a plan item; timed units wait in their phase until due; the plan
opens with what ran and how much of her day she's used."""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from scheduling import templates as T
from scheduling.day_phase import DayPhase
from scheduling.day_turn import DayPlanTool, _run_at, menu_text

PLANS = [{"plan": "creative-expr", "title": "Creative Expression", "goal": "",
          "phase": {"number": 1, "of": 3, "title": "Practice"},
          "open": [{"kind": "build", "title": "Establish weekly creative rhythm"}], "loose": []},
         {"plan": "honesty", "title": "Direct Honesty", "goal": "", "phase": None,
          "open": [{"kind": "ask", "title": "Reach out to Kohl"}], "loose": []}]
NOW = datetime(2026, 11, 18, 7, 0)


class _WS:
    root = "/nonexistent"

    def __init__(self):
        self.files = {}

    def run(self, name, a, session_id=""):
        self.files[a["path"]] = a["content"]
        return "ok"


def _tool(tmp_path, *ids):
    menu = [T.WORK_TEMPLATES[i].instantiate() for i in ids]
    return DayPlanTool(menu, [DayPhase.MORNING, DayPhase.AFTERNOON, DayPhase.NIGHT], _WS(),
                       plans=PLANS, now=NOW, data_dir=tmp_path)


def test_a_time_must_be_in_its_phase_and_still_ahead():
    assert _run_at("09:30", DayPhase.MORNING, NOW) == ("2026-11-18T09:30", None)
    assert "isn't in afternoon" in _run_at("09:30", DayPhase.AFTERNOON, NOW)[1]
    assert "already passed" in _run_at("06:30", DayPhase.MORNING, NOW)[1]
    assert "can read" in _run_at("half nine", DayPhase.MORNING, NOW)[1]
    late = datetime(2026, 11, 18, 23, 0)
    assert _run_at("01:00", DayPhase.NIGHT, late) == ("2026-11-19T01:00", None)


def test_items_carry_a_time_and_a_plan_item_into_their_sessions(tmp_path):
    tool = _tool(tmp_path, "writing_session", "growth_edge_work")
    out = tool({"plan": {
        "morning": [{"template_id": "writing_session", "at": "09:00", "focus": "a song lyric",
                     "plan": "Creative Expression", "item": "establish weekly creative rhythm"}],
        "afternoon": [{"template_id": "growth_edge_work", "at": "14:30"}]}})
    assert out.startswith("Plan set: 2")
    units = tool.work_units(T.WORK_TEMPLATES)
    w = units[DayPhase.MORNING][0]
    assert w.run_at == "2026-11-18T09:00"
    assert w.plan_item == {"plan": "creative-expr", "plan_title": "Creative Expression",
                           "item": "Establish weekly creative rhythm"}
    assert w.focus.startswith("a song lyric (For my plan") and "babelr_plans set_item" in w.focus
    assert units[DayPhase.AFTERNOON][0].plan_item is None
    from scheduling.day_recap import last_carried
    assert set(last_carried(tmp_path)) == {"creative-expr"}
    assert "09:00 Writing Session [Creative Expression: Establish weekly creative rhythm]" in \
        tool.workspace.files["DAY_PLAN.md"]
    # The fields survive the queue's file.
    from scheduling.work_unit import WorkUnit
    again = WorkUnit.from_dict(w.to_dict())
    assert again.run_at == w.run_at and again.plan_item == w.plan_item


def test_a_wrong_plan_item_sets_nothing_and_says_whats_open(tmp_path):
    tool = _tool(tmp_path, "writing_session")
    out = tool({"plan": {"morning": [{"template_id": "writing_session", "plan": "Direct Honesty",
                                      "item": "Speak at last"}]}})
    assert "isn't an open item" in out["error"] and "Reach out to Kohl" in out["error"]
    assert tool.chosen is None
    out = tool({"plan": {"morning": [{"template_id": "writing_session", "plan": "Gardening", "item": "x"}]}})
    assert "isn't one of my plans" in out["error"] and "Creative Expression" in out["error"]


def test_the_menu_says_how_much_room_there_is():
    text = menu_text([], [DayPhase.MORNING], 4.9, usage="Over the last 7 days I ran about 6 sessions a day")
    assert "about 6 sessions a day" in text and "up to 12" in text and "more than one of my plans" in text


def test_timed_units_wait_in_their_phase_until_due():
    from scheduling.phase_queue import PhaseQueueManager
    pq = PhaseQueueManager()
    sent = []

    async def dispatch(q):
        sent.append(q.work_unit.name)
        return True
    pq._dispatch_work = dispatch
    later = T.WORK_TEMPLATES["writing_session"].instantiate()
    later.run_at = (datetime.now() + timedelta(hours=1)).isoformat(timespec="minutes")
    now_unit = T.WORK_TEMPLATES["reflection_block"].instantiate()
    pq.queue_for_phase(later, DayPhase.MORNING)
    pq.queue_for_phase(now_unit, DayPhase.MORNING)
    asyncio.run(pq._take_and_dispatch(DayPhase.MORNING))
    assert sent == [now_unit.name]
    assert asyncio.run(pq.dispatch_due(DayPhase.MORNING)) == 0
    later.run_at = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes")
    assert asyncio.run(pq.dispatch_due(DayPhase.MORNING)) == 1
    assert sent == [now_unit.name, later.name] and not pq._phase_queues[DayPhase.MORNING]


def test_the_phase_tick_runs_its_callbacks():
    from scheduling.day_phase import DayPhaseTracker
    tracker = DayPhaseTracker.__new__(DayPhaseTracker)
    tracker._running, tracker._current_phase = True, None
    tracker._on_tick_callbacks, ticks = [], []
    tracker.get_phase_for_time = lambda: None

    async def tick():
        ticks.append(1)
    tracker.on_tick(tick)
    asyncio.run(tracker.check_phase())
    assert ticks == [1]


def _log(root, kind, at, cost=0.1, seconds=120, summary=""):
    d = root / "session_logs" / kind / at.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{at:%H%M%S}_{kind}.json").write_text(json.dumps({
        "session_type": kind, "started_at": at.isoformat(), "estimated_cost_usd": cost,
        "duration_seconds": seconds, "summary": summary, "status": "completed"}))


def test_the_recap_shows_what_ran_and_the_room_left(tmp_path):
    from scheduling.day_recap import since_last_plan, usage_line
    now = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    for d in range(1, 8):
        for h in (9, 13, 19):
            _log(tmp_path, "growth_edge", now - timedelta(days=d, hours=-h + 7))
    _log(tmp_path, "day_planning", now - timedelta(hours=20))
    _log(tmp_path, "growth_edge", now - timedelta(hours=19), summary="Sent Kohl the message I'd prepared.")
    _log(tmp_path, "growth_edge", now - timedelta(hours=15))
    _log(tmp_path, "growth_edge", now - timedelta(hours=10))
    line = usage_line(tmp_path, now=now)
    # 21 over the week before + 4 yesterday = 25 in 7 days, $0.10 each
    assert "about 4 sessions a day" in line and "$0.36 of my $5.00" in line and "room for roughly 46" in line
    ws = SimpleNamespace(root=tmp_path)
    (tmp_path / "DAY_PLAN.md").write_text("# My plan for yesterday\n- Growth Edge Work")
    text = since_last_plan(ws, tmp_path, now=now)
    assert "# My plan for yesterday" in text and "Sent Kohl the message I'd prepared." in text
    assert "(5 of these 5 were growth_edge.)" in text  # two of the week's fall after that plan


def test_her_plans_say_when_a_day_last_carried_them():
    from long_term_planning_turn import working_toward_text
    now = datetime(2026, 11, 18, 7, 0)
    text = working_toward_text(PLANS, offered=False, now=now, carried={"honesty": "2026-11-17T06:02:00"})
    assert "Last carried by a day plan: yesterday." in text
    assert "Not yet carried by a day plan item." in text


# The shape of her day: kinds, and her own counts (Kohl's idea, 2026-11-17).

def test_every_menu_template_has_a_kind():
    from scheduling.day_shape import UNSHAPED, kind_of
    missing = [t for t in T.WORK_TEMPLATES if t not in UNSHAPED and not kind_of(t)]
    assert missing == [], "a new template needs a kind in day_shape.KINDS"


def test_she_sets_her_shape_and_a_short_plan_is_named_not_refused(tmp_path):
    from scheduling import day_shape as S
    shape, mine, _ = S.read_shape(tmp_path)
    assert not mine and shape == S.STARTING_SHAPE
    assert "isn't" not in str(S.set_shape({"shape": {"making": 2, "out": 0}, "why": "more making"}, tmp_path))
    shape, mine, why = S.read_shape(tmp_path)
    assert mine and shape == {"inward": 1, "learning": 1, "making": 2, "out": 0} and why == "more making"
    assert "Not a kind" in S.set_shape({"shape": {"sleep": 1}}, tmp_path)["error"]
    assert "0 to 12" in S.set_shape({"shape": {"making": 40}}, tmp_path)["error"]

    tool = _tool(tmp_path, "writing_session", "growth_edge_work")
    out = tool({"plan": {"morning": [{"template_id": "writing_session"}],
                         "afternoon": [{"template_id": "growth_edge_work"}]}})
    assert out.startswith("Plan set: 2") and tool.chosen is not None
    assert "Short of my day shape" in out and "learning 0 of 1" in out and "making 1 of 2" in out
    assert "out" not in out.split("Short of my day shape")[1].split(".")[0]  # 0 wanted


def test_what_ran_today_counts_toward_her_shape(tmp_path):
    from scheduling import day_shape as S
    _log(tmp_path, "research", NOW.replace(hour=6, minute=30))
    assert S.ran_today(tmp_path, NOW)["learning"] == 1
    assert not any(m.startswith("learning") for m in S.shortfall([], tmp_path, NOW))
    assert "(1 done today)" in S.shape_text(tmp_path, NOW)


def test_the_menu_is_grouped_by_kind_and_shows_the_shape():
    menu = [T.WORK_TEMPLATES[i].instantiate() for i in ("music", "social", "reflection_block")]
    text = menu_text(menu, [DayPhase.MORNING], 4.9, shape="A starting day shape, until I set my own")
    assert text.index("Inward:") < text.index("- reflection_block") < text.index("Making:") \
        < text.index("- music") < text.index("Out in the world:") < text.index("- social")
    assert "A starting day shape" in text


def test_set_day_shape_is_offered_in_day_planning():
    from agent_loop.spec import session_spec
    assert {"set_day_plan", "set_day_shape", "babelr_plans"} <= set(session_spec("day_planning").tool_names())


# Her routines: on a schedule, run on their own; her plan adds to them.

def test_she_makes_changes_and_removes_routines(tmp_path):
    from scheduling import routines as R
    assert "none yet" in R.routines_text(data_dir=tmp_path)
    out = R.set_routine({"action": "add", "template_id": "social", "at": "15:00", "days": "weekdays",
                         "name": "Bluesky"}, tmp_path)
    rid = out["routine"]["id"]
    assert out["routine"]["routine"] == "15:00 weekdays: social (Bluesky)"
    assert "isn't on my menu" in R.set_routine({"action": "add", "template_id": "day_planning",
                                                "at": "9:00"}, tmp_path)["error"]
    assert "HH:MM" in R.set_routine({"action": "add", "template_id": "social", "at": "noon"}, tmp_path)["error"]
    R.set_routine({"action": "change", "id": rid, "days": ["mon", "thu"], "focus": "my inbox"}, tmp_path)
    assert R.set_routine({"action": "list"}, tmp_path)["my_routines"][0]["routine"] == \
        "15:00 mon, thu: social (Bluesky), focus: my inbox"
    assert R.set_routine({"action": "remove", "id": rid}, tmp_path)["success"]
    assert R.routines(tmp_path) == []


def test_routines_queue_in_their_phase_once_a_day(tmp_path, levers):
    from scheduling import routines as R
    from scheduling.phase_queue import PhaseQueueManager
    R.set_routine({"action": "add", "template_id": "reflection_block", "at": "08:00", "focus": "the week"},
                  tmp_path)
    R.set_routine({"action": "add", "template_id": "research_block", "at": "14:00"}, tmp_path)
    R.set_routine({"action": "add", "template_id": "writing_session", "at": "09:00", "days": ["sun"]},
                  tmp_path)   # 2026-11-18 is a Wednesday
    pq = PhaseQueueManager()
    assert R.queue_due_phase(DayPhase.MORNING, pq, now=NOW, data_dir=tmp_path) == 1
    assert R.queue_due_phase(DayPhase.MORNING, pq, now=NOW, data_dir=tmp_path) == 0  # once a day
    q = pq._phase_queues[DayPhase.MORNING][0].work_unit
    assert (q.template_id, q.run_at, q.focus) == ("reflection_block", "2026-11-18T08:00", "the week")
    # An hour past its time (a restart): skipped, not run late.
    pq2 = PhaseQueueManager()
    assert R.queue_due_phase(DayPhase.MORNING, pq2, now=NOW.replace(hour=9, minute=30), data_dir=tmp_path) == 0
    # Still to come today, they count toward her shape.
    from scheduling.day_shape import shortfall
    assert not any(m.startswith("learning") for m in shortfall([], tmp_path, NOW))
    assert "[today]" in R.routines_text(NOW, tmp_path)


def test_routines_are_offered_in_day_planning():
    from agent_loop.spec import session_spec
    assert "set_routine" in session_spec("day_planning").tool_names()


def test_consolidation_keeps_whats_changing_at_the_top_of_her_agenda():
    from agent_loop.workspace import AGENDA_CONTEXT_CHARS
    from session.prompts import get_session_prompt
    text = get_session_prompt("consolidation")
    assert "keep what's changing at its top" in text
    assert f"{AGENDA_CONTEXT_CHARS:,} characters" in text, "the number she's told must be the real cap"


# Her asks, 2026-11-18: refusals named, budget by kind, drops with the
# arithmetic, and what she actually sent beside what ran.

def test_the_recap_names_refusals_and_what_she_actually_sent(tmp_path):
    from scheduling.day_recap import since_last_plan
    now = datetime(2026, 11, 18, 7, 0)
    _log(tmp_path, "day_planning", now - timedelta(hours=20))
    refused = lambda since: [{"work_name": "phase.knowledge_building", "started_at": "2026-11-17T14:00:00",  # noqa: E731
                              "error": "research budget exhausted ($0.30 needed, $0.12 left)"}]
    sent = lambda since: [{"at": datetime(2026, 11, 17, 12, 1), "what": "to Kohl (share) via app",  # noqa: E731
                           "text": "I'm not ready to be less careful with you yet."}]
    text = since_last_plan(SimpleNamespace(root=tmp_path), tmp_path, now=now, refused=refused, sent=sent)
    assert "Planned but refused (not run):\n- 14:00 knowledge_building: research budget exhausted" in text
    assert "What I actually sent out since then:\n- Tue 12:01 to Kohl (share) via app: \"I'm not ready" in text
    nothing = since_last_plan(SimpleNamespace(root=tmp_path), tmp_path, now=now,
                              refused=lambda s: [], sent=lambda s: [])
    assert "I sent nothing out since then" in nothing and "refused" not in nothing


def test_the_menu_shows_budget_by_kind_and_names_what_it_left_off():
    text = menu_text([], [DayPhase.MORNING], 4.2, unavailable=["Knowledge Building (needs $0.30; research has $0.12 left today)"],
                     budget_by_category={"research": 0.12, "reflection": 0.9})
    assert "By kind of work: research $0.12, reflection $0.90." in text
    assert "Not available today: Knowledge Building (needs $0.30; research has $0.12 left today)." in text


def test_the_engine_names_over_budget_templates(monkeypatch):
    from scheduling.decision_engine import DecisionContext, SchedulingDecisionEngine
    eng = SchedulingDecisionEngine.__new__(SchedulingDecisionEngine)
    ctx = DecisionContext.__new__(DecisionContext)
    ctx.budget_by_category = {k: 0.0 for k in ("research", "reflection", "growth", "curiosity", "system")}
    ctx.is_idle = True
    eng._get_viable_candidates(ctx)
    assert any("needs $" in u and "left today" in u for u in eng._unavailable)
