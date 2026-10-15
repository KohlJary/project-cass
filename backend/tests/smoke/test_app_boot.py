"""
Smoke (a): the real app boots under CASS_PROFILE=test and starts nothing on its own.
"""
from tests.smoke.conftest import backend_tasks


def test_app_boots_and_health_is_ok(booted_app):
    response = booted_app.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_heavy_components_and_chat_path_initialized(booted_app):
    import main_sdk
    import websocket_handlers

    assert main_sdk.memory is not None
    assert main_sdk.self_model_graph is not None
    assert websocket_handlers._state["memory"] is not None
    assert websocket_handlers._state["agent_client"] is not None


def test_no_background_loop_started_under_test_profile(booted_app):
    """With every lever off, no Cass coroutine should be left running."""
    import main_sdk
    from routes.admin.scheduler import get_scheduler

    assert backend_tasks(booted_app) == []

    # And the long-lived objects that own loops report themselves idle.
    assert main_sdk.thymos_runner.running is False
    synkratos = get_scheduler()
    assert synkratos is not None and synkratos._running is False
    assert synkratos.system_tasks == {}  # no system job registered


def test_no_llm_called_during_boot(booted_app, fake_llm):
    assert fake_llm.calls == []


def test_feature_endpoint_mounted_behind_admin_auth(booted_app):
    assert booted_app.get("/admin/features").status_code == 401
