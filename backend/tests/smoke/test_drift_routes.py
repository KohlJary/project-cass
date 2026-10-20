"""
Routes added so the admin and TUI frontends stop calling missing endpoints
(see test_frontend_endpoints.py). Each test drives the route through the
booted app with a real admin token.
"""
import pytest

from tests.smoke.conftest import admin_token, create_user, module_app


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    return app.db_path


@pytest.fixture(scope="module")
def admin(app):
    user_id = create_user("Drift Admin", is_admin=True)
    return {"Authorization": f"Bearer {admin_token(user_id)}"}


def test_testing_health_reports_components(app, admin):
    resp = app.get("/testing/health", headers=admin)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("fingerprint_analyzer", "test_runner", "drift_detector",
                "pre_deploy_validator", "rollback_manager"):
        assert body[key] is True, key
    assert body["status"] == "healthy"
    assert body["baseline_set"] is False
    # The A/B framework was retired (#47); health no longer reports it.
    assert "ab_testing_framework" not in body
    assert "active_experiments" not in body


def test_testing_health_requires_auth(app):
    assert app.get("/testing/health").status_code == 401


@pytest.mark.parametrize("path", [
    "/testing/ab/experiments",
    "/testing/temporal/statistics",
    "/testing/authenticity/alerts",
    "/testing/authenticity/ml/status",
])
def test_retired_testing_routes_are_gone(app, admin, path):
    # #47: the A/B, authenticity alert/ML and temporal-metrics subsystems
    # were retired (kept on attic/stabilization), not wired.
    assert app.get(path, headers=admin).status_code == 404


def test_research_schedule_approval_flow(app, admin):
    import main_sdk

    request = main_sdk.research_scheduler.request_session(
        focus_description="Read about predictive processing", session_type="research")
    schedule_id = request["schedule_id"]

    pending = app.get("/admin/research/schedules/pending", headers=admin).json()
    assert schedule_id in [s["schedule_id"] for s in pending["schedules"]]

    got = app.get(f"/admin/research/schedules/{schedule_id}", headers=admin)
    assert got.status_code == 200 and got.json()["schedule"]["status"] == "pending_approval"

    approved = app.post(f"/admin/research/schedules/{schedule_id}/approve", json={}, headers=admin)
    assert approved.status_code == 200, approved.text
    assert app.post(f"/admin/research/schedules/{schedule_id}/pause", headers=admin).status_code == 200
    assert app.post(f"/admin/research/schedules/{schedule_id}/resume", headers=admin).status_code == 200

    listed = app.get("/admin/research/schedules", headers=admin).json()["schedules"]
    assert [s["status"] for s in listed if s["schedule_id"] == schedule_id] == ["approved"]
    stats = app.get("/admin/research/schedules/stats", headers=admin).json()
    assert stats["by_status"].get("approved", 0) >= 1

    # Rejecting an approved schedule is refused with the scheduler's reason.
    rejected = app.post(f"/admin/research/schedules/{schedule_id}/reject",
                        json={"reason": "no"}, headers=admin)
    assert rejected.status_code == 400 and "not pending" in rejected.json()["detail"]
    assert app.get("/admin/research/schedules/nope", headers=admin).status_code == 404


def test_research_notes_by_session(app, admin):
    from datetime import datetime
    import main_sdk
    from database import get_db

    # research_notes.session_id references research_sessions(id).
    with get_db() as conn:
        for sid in ("sess-1", "sess-2"):
            conn.execute("INSERT INTO research_sessions (id, daemon_id, started_at) VALUES (?, ?, ?)",
                         (sid, main_sdk._daemon_id, datetime.now().isoformat()))

    note = main_sdk.research_manager.create_research_note(
        title="Petrichor", content="The smell of rain " * 30, session_id="sess-1")
    note_id = note["note_id"]
    main_sdk.research_manager.create_research_note(title="Other", content="x", session_id="sess-2")

    by_session = app.get("/admin/research/notes/session/sess-1", headers=admin).json()
    assert [n["note_id"] for n in by_session["notes"]] == [note_id]
    assert len(by_session["notes"][0]["content"]) > 200  # full content for the session view

    filtered = app.get("/admin/research/notes", params={"session_id": "sess-2"}, headers=admin).json()
    assert [n["title"] for n in filtered["notes"]] == ["Other"]

    one = app.get(f"/admin/research/notes/{note_id}", headers=admin)
    assert one.status_code == 200 and one.json()["note"]["title"] == "Petrichor"
    assert app.get("/admin/research/notes/missing", headers=admin).status_code == 404


def test_journal_lock_and_unlock(app, admin):
    import main_sdk

    with pytest.MonkeyPatch.context() as mp:
        state = {}
        mp.setattr(main_sdk.memory, "set_journal_locked",
                   lambda date, locked: state.update({date: locked}) or date == "2026-10-01")
        locked = app.post("/journal/2026-10-01/lock", headers=admin)
        assert locked.status_code == 200 and locked.json() == {"date": "2026-10-01", "locked": True}
        assert app.post("/journal/2026-10-01/unlock", headers=admin).json()["locked"] is False
        assert state == {"2026-10-01": False}
        assert app.post("/journal/2026-01-01/lock", headers=admin).status_code == 404
