"""Smoke: the admin PeopleDex route marks a house agent (plan "Cass's memory", a8fb4c8f)."""
import pytest

from tests.smoke.conftest import create_user, module_app


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    return app.db_path


def test_mark_an_entity_as_a_house_agent(app, smoke_admin):
    from memory.scope import house_agent_user_ids
    from peopledex import PeopleDexManager
    headers = {"Authorization": f"Bearer {smoke_admin[1]}"}
    uid = create_user("Quillwright")
    PeopleDexManager().ensure_entity_for_user(uid)

    found = app.get("/admin/peopledex/entities", params={"name": "Quillwright"}, headers=headers).json()
    [entity] = [e for e in found["entities"] if e["user_id"] == uid]
    assert entity["entity_type"] == "person" and uid not in house_agent_user_ids()

    r = app.patch(f"/admin/peopledex/entities/{entity['id']}", json={"entity_type": "daemon"}, headers=headers)
    assert r.status_code == 200 and r.json()["entity"]["entity_type"] == "daemon"
    assert uid in house_agent_user_ids()

    assert app.patch(f"/admin/peopledex/entities/{entity['id']}", json={"entity_type": "robot"},
                     headers=headers).status_code == 422
    assert app.patch("/admin/peopledex/entities/nope", json={"entity_type": "daemon"},
                     headers=headers).status_code == 404
