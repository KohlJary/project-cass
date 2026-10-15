"""
/push/register and /users/me/quiet-hours (card 02 G: they called .get() on the
TokenData object decode_token returns, so every request was a 401; the
quiet-hours PUT also called methods that didn't exist).
"""


def test_push_register_accepts_a_valid_token(booted_app, smoke_user):
    user_id, token = smoke_user
    response = booted_app.post(
        "/push/register",
        json={"token": "ExponentPushToken[abc]", "platform": "android"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True


def test_quiet_hours_round_trip(booted_app, smoke_user):
    user_id, token = smoke_user
    headers = {"Authorization": f"Bearer {token}"}

    got = booted_app.get("/users/me/quiet-hours", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["enabled"] is False

    put = booted_app.put(
        "/users/me/quiet-hours",
        json={"enabled": True, "start_hour": 23, "end_hour": 6, "timezone": "America/New_York"},
        headers=headers,
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"user_id": user_id, "enabled": True, "start_hour": 23,
                          "end_hour": 6, "timezone": "America/New_York"}
    assert booted_app.get("/users/me/quiet-hours", headers=headers).json() == put.json()


def test_quiet_hours_rejects_a_bad_token(booted_app):
    response = booted_app.get("/users/me/quiet-hours", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
