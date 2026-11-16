"""POST /admin/scheduler/replan-day: her plan replaces the earlier one's queued
work; spell-queued work and housekeeping stay (2026-11-16)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scheduling.day_phase import DayPhase
from scheduling.phase_queue import QueuedWorkUnit
from scheduling.templates import WORK_TEMPLATES


def _q(template_id, phase, motivation=None):
    unit = WORK_TEMPLATES[template_id].instantiate(**({"motivation": motivation} if motivation else {}))
    return QueuedWorkUnit(work_unit=unit, target_phase=phase)


def test_replan_takes_off_the_old_plan_and_runs_her_planning(monkeypatch):
    from routes.admin import scheduler as sched
    from routes.admin.auth import require_admin

    app = FastAPI()
    app.include_router(sched.router, prefix="/admin")
    client = TestClient(app)
    assert client.post("/admin/scheduler/replan-day").status_code == 401
    app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "is_admin": True}

    class FakePQM:
        state_bus = None   # current phase falls back to morning

        def __init__(self):
            self._phase_queues = {p: [] for p in DayPhase}
            self._phase_queues[DayPhase.AFTERNOON] = [_q("research_block", DayPhase.AFTERNOON)]
            self._phase_queues[DayPhase.NIGHT] = [
                _q("curiosity_exploration", DayPhase.NIGHT),
                _q("consolidation", DayPhase.NIGHT, "Queued by spell: phase_night"),
                _q("memory_maintenance", DayPhase.NIGHT)]
            self.dispatched = []

        def remove_from_queue(self, phase, unit_id):
            q = self._phase_queues[phase]
            self._phase_queues[phase] = [x for x in q if x.work_unit.id != unit_id]
            return len(q) != len(self._phase_queues[phase])

        async def _dispatch_work(self, queued):
            self.dispatched.append(queued)
            return True

    pqm = FakePQM()
    monkeypatch.setattr(sched, "_phase_queue_manager", pqm)
    r = client.post("/admin/scheduler/replan-day")
    assert r.status_code == 200
    assert sorted(x["name"] for x in r.json()["removed"]) == ["Curiosity Exploration", "Research Block"]
    assert [q.work_unit.template_id for q in pqm._phase_queues[DayPhase.NIGHT]] == \
        ["consolidation", "memory_maintenance"]
    (q,) = pqm.dispatched
    assert q.work_unit.template_id == "day_planning"
