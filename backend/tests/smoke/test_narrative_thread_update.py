"""
Issue #79: PATCH /admin/narrative/threads/{id} passed thread_type to
ThreadManager.update_thread, which didn't accept it, so every PATCH was a
500. update_thread now takes thread_type; an unknown type is a 422.
"""


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _new_thread(app, headers):
    r = app.post("/admin/narrative/threads", json={"title": "Old title"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_patch_thread_title(booted_app, smoke_admin):
    _admin, token = smoke_admin
    h = _bearer(token)
    thread_id = _new_thread(booted_app, h)

    r = booted_app.patch(f"/admin/narrative/threads/{thread_id}",
                         json={"title": "New title"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "New title"
    assert r.json()["thread_type"] == "topic"


def test_patch_thread_type(booted_app, smoke_admin):
    _admin, token = smoke_admin
    h = _bearer(token)
    thread_id = _new_thread(booted_app, h)

    r = booted_app.patch(f"/admin/narrative/threads/{thread_id}",
                         json={"thread_type": "project"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["thread_type"] == "project"
    assert r.json()["title"] == "Old title"


def test_patch_thread_unknown_type_is_422(booted_app, smoke_admin):
    _admin, token = smoke_admin
    h = _bearer(token)
    thread_id = _new_thread(booted_app, h)

    r = booted_app.patch(f"/admin/narrative/threads/{thread_id}",
                         json={"thread_type": "nonsense"}, headers=h)
    assert r.status_code == 422, r.text
