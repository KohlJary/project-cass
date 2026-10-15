"""
Lever wiring checks that need the full runtime dependencies (anthropic SDK,
python-multipart via the admin routers), so they live with the smoke batteries
rather than in the fast suite. The rest are in tests/test_features.py.
"""
import asyncio

import features


class TestLeverWiring:
    def test_endpoint_lists_levers_and_requires_admin(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.admin import features as features_route
        from routes.admin.auth import require_admin

        app = FastAPI()
        app.include_router(features_route.router, prefix="/admin")
        client = TestClient(app)

        assert client.get("/admin/features").status_code == 401

        app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "is_admin": True}
        body = client.get("/admin/features").json()
        rows = {row["name"]: row for row in body["levers"]}
        assert body["profile"] == "test"
        assert rows["thymos"]["enabled"] is False
        assert rows["thymos"]["source"] == "profile:test"
        assert set(rows) == set(features.LEVERS)

    async def test_phase_change_email_check_respects_lever(self, levers, monkeypatch):
        from scheduling.phase_queue import PhaseQueueManager
        from scheduling.day_phase import DayPhase, PhaseTransition

        pqm = PhaseQueueManager.__new__(PhaseQueueManager)
        checks, dispatches = [], []

        async def fake_email(phase, respond_to_all=True):
            checks.append(phase)

        async def fake_dispatch(*a, **k):
            dispatches.append(a)

        monkeypatch.setattr(pqm, "_check_email_on_phase_change", fake_email, raising=False)
        monkeypatch.setattr(pqm, "_delayed_phase_dispatch", fake_dispatch, raising=False)
        transition = PhaseTransition.__new__(PhaseTransition)
        transition.to_phase = DayPhase.MORNING

        await pqm.on_phase_changed(transition)
        await asyncio.sleep(0)
        assert checks == [] and len(dispatches) == 1

        with levers(phase_email=True):
            await pqm.on_phase_changed(transition)
            await asyncio.sleep(0)
        assert checks == [DayPhase.MORNING]

    def test_late_source_registration_respects_capability_indexing(self, levers, monkeypatch):
        """Sources registered after boot must not start Ollama-backed indexing when the lever is off."""
        from state_bus import GlobalStateBus

        bus = GlobalStateBus.__new__(GlobalStateBus)
        bus._queryable_sources = {}
        bus._capability_registry = object()
        started = []

        async def fake_index(source):
            started.append(source)

        monkeypatch.setattr(bus, "_register_source_capabilities", fake_index, raising=False)

        class Source:
            source_id = "late"
            _is_registered = False

            class refresh_strategy:  # anything but SCHEDULED
                value = "lazy"

        async def register():
            bus.register_source(Source())
            await asyncio.sleep(0)

        asyncio.run(register())
        assert started == []

        with levers(capability_indexing=True):
            asyncio.run(register())
        assert len(started) == 1
