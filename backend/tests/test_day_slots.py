"""Time through her day (plan "Cass plans her own day", phase 4): 90-minute slots across
the waking day, plans to a time or a phase, one session at a time, what a plan takes, and
her own notes beside her options."""
import asyncio
from datetime import datetime, timedelta

from scheduling import slots as S
from scheduling import templates as T
from scheduling.day_phase import DayPhase
from scheduling.day_shape import read_shape, read_usually, set_shape
from scheduling.day_turn import DayPlanTool, menu_text

NOW = datetime(2026, 11, 19, 7, 0)


class _WS:
    root = "/nonexistent"

    def __init__(self):
        self.files = {}

    def run(self, name, a, session_id=""):
        self.files[a["path"]] = a["content"]
        return "ok"


def _tool(tmp_path, *ids, budget=4.0, now=NOW):
    menu = [T.WORK_TEMPLATES[i].instantiate() for i in ids]
    return DayPlanTool(menu, [DayPhase.MORNING, DayPhase.AFTERNOON, DayPhase.EVENING, DayPhase.NIGHT],
                       _WS(), now=now, data_dir=tmp_path, budget_remaining=budget)


def test_the_waking_day_is_eleven_90_minute_slots():
    times = [t.strftime("%H:%M") for t in S.slot_times(NOW)]
    assert times == ["06:00", "07:30", "09:00", "10:30", "12:00", "13:30", "15:00", "16:30",
                     "18:00", "19:30", "21:00"]
    assert [S.phase_of(t) for t in S.slot_times(NOW)].count("evening") == 3
    assert [t.strftime("%H:%M") for t in S.slots_left(NOW, "morning")] == ["07:30", "09:00", "10:30"]


def test_phase_only_items_spread_and_a_timed_one_keeps_its_slot(tmp_path):
    tool = _tool(tmp_path, "reflection_block", "writing_session", "research_block")
    out = tool({"plan": {"morning": [{"template_id": "reflection_block"},
                                     {"template_id": "writing_session", "at": "07:45"},
                                     {"template_id": "research_block"}]}})
    assert "Plan set: 3" in out
    at = {i["template_id"]: i["at"][11:16] for i in tool.chosen["morning"]}
    # 07:30 is taken by the 07:45 item, so the others take 09:00 and 10:30.
    assert at == {"reflection_block": "09:00", "writing_session": "07:45", "research_block": "10:30"}
    units = tool.work_units(T.WORK_TEMPLATES)[DayPhase.MORNING]
    assert all(u.run_at for u in units)


def test_overflow_waits_at_the_phase_last_slot_and_never_spills(tmp_path):
    ids = ["reflection_block", "writing_session", "research_block", "growth_edge_work"]
    tool = _tool(tmp_path, *ids)
    out = tool({"plan": {"morning": [{"template_id": i} for i in ids], "night": [{"template_id": "reflection_block"}]}})
    ats = [i["at"][11:16] for i in tool.chosen["morning"]]
    assert ats == ["07:30", "09:00", "10:30", "10:30"]          # 4 items, 3 morning slots left
    assert tool.chosen["night"][0]["at"] is None                # night isn't slotted
    assert "will wait their turn" not in out                    # 4 day items, 10 slots left today
    assert "about $" in out and "of $4.00 left" in out


def test_a_time_goes_to_the_phase_it_falls_in(tmp_path):
    tool = _tool(tmp_path, "research_block")
    tool({"plan": {"morning": [{"template_id": "research_block", "at": "14:30"}]}})
    assert tool.chosen["morning"] == []
    assert tool.chosen["afternoon"][0]["at"].endswith("14:30")


def test_the_menu_names_slots_left_and_what_filling_them_costs():
    line = S.menu_line(NOW, budget_left=5.0, costs=[0.2, 0.4])
    assert "Slots left today: 10" in line and "the next at 07:30" in line
    assert "about $3.00 of the $5.00 left" in line
    assert "No slots left" in S.menu_line(datetime(2026, 11, 19, 21, 30))
    text = menu_text([], [DayPhase.MORNING], 4.9)
    assert "90-minute slots" in text and "up to 12" in text


def test_her_notes_sit_beside_her_options_and_dont_claim_a_shape(tmp_path, monkeypatch):
    assert set_shape({"usually": {"social": "usually one a day, more when it calls"}}, tmp_path)["success"]
    shape, mine, _ = read_shape(tmp_path)
    assert not mine                                    # notes alone don't make a shape hers
    assert read_usually(tmp_path) == {"social": "usually one a day, more when it calls"}
    set_shape({"shape": {"out": 2}}, tmp_path)
    assert read_shape(tmp_path)[1] and read_usually(tmp_path)    # setting a shape keeps her notes
    set_shape({"usually": {"social": ""}}, tmp_path)
    assert read_usually(tmp_path) == {} and read_shape(tmp_path)[1]
    import scheduling.day_shape as DS
    monkeypatch.setattr(DS, "read_usually", lambda data_dir=None: {"social": "when it calls"})
    text = menu_text([T.WORK_TEMPLATES["social"].instantiate()], [DayPhase.MORNING], 4.0)
    assert "My own note: when it calls" in text


def test_one_session_at_a_time_and_one_unit_per_tick(monkeypatch):
    from scheduling.phase_queue import PhaseQueueManager
    import agent_loop.felt as felt
    pq = PhaseQueueManager()
    sent = []

    async def dispatch(q):
        sent.append(q.work_unit.name)
        return True
    pq._dispatch_work = dispatch
    a = T.WORK_TEMPLATES["writing_session"].instantiate()
    b = T.WORK_TEMPLATES["reflection_block"].instantiate()
    a.run_at = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="minutes")
    b.run_at = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes")
    pq.queue_for_phase(b, DayPhase.MORNING)
    pq.queue_for_phase(a, DayPhase.MORNING)
    felt._RUNNING["s1"] = (datetime.now(), 30)
    try:
        assert asyncio.run(pq.dispatch_due(DayPhase.MORNING)) == 0     # a session is running
    finally:
        felt._RUNNING.pop("s1", None)
    assert asyncio.run(pq.dispatch_due(DayPhase.MORNING)) == 1
    assert sent == [a.name]                                            # earliest first, one per tick
    assert asyncio.run(pq.dispatch_due(DayPhase.MORNING)) == 1
    assert sent == [a.name, b.name]


def test_a_session_that_never_said_it_ended_stops_holding_the_queue():
    import agent_loop.felt as felt
    felt._RUNNING["old"] = (datetime.now() - timedelta(hours=3), 30)
    try:
        assert "old" not in felt.running()
    finally:
        felt._RUNNING.pop("old", None)
    felt.session_started(None, "reflection", "s2", None, 30)
    assert "s2" in felt.running()
    felt.session_ended(None, "reflection", "s2", "completed", None, 1.0, 1, 0)
    assert "s2" not in felt.running()
