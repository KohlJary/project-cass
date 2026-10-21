"""
Issue #48: GET /testing/authenticity/content/patterns imported three names
testing.content_markers never defined, so it was an ImportError -> 500. It
now returns the pattern groups the module actually uses.
"""


def test_content_patterns_route_returns_200(booted_app, smoke_admin):
    _admin, token = smoke_admin
    r = booted_app.get("/testing/authenticity/content/patterns",
                       headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["curiosity_patterns"]
    assert body["emote_emotion_map"]
    for key, value in body.items():
        assert value, key
