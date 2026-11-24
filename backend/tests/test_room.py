"""
Her room in Chapter House, phase 2 (the read-only feed): nothing shows that
she didn't share; Kohl's token sees what she shared, the house's only what
she shared with the house; the feed only reads.
"""
import asyncio
import json
from datetime import datetime

import pytest

from room import Room, audience_for, mint_token


@pytest.fixture
def room(tmp_path, daemon_id, monkeypatch):
    import config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    from database import get_db
    img = tmp_path / "images" / "tide.png"
    img.parent.mkdir()
    img.write_bytes(b"\x89PNG fake")
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO generated_images (id, daemon_id, prompt, style, purpose, image_path, created_at) "
                     "VALUES ('img-1', ?, 'the tide at dusk', 'painterly', 'autonomous', ?, ?)",
                     (daemon_id, str(img), now))
        conn.execute("INSERT INTO image_artist_notes (image_id, daemon_id, chosen_by, subject, why, artist_note, "
                     "created_at) VALUES ('img-1', ?, 'cass', 'The tide', 'it stayed with me', "
                     "'The light came out softer than I meant.', ?)", (daemon_id, now))
        conn.execute("INSERT INTO journals (id, daemon_id, date, content, created_at) "
                     "VALUES ('j-1', ?, '2026-11-13', 'A long day of building.', ?)", (daemon_id, now))
        conn.execute("INSERT INTO journals (id, daemon_id, date, content, created_at) "
                     "VALUES ('j-2', ?, '2026-11-12', 'Not ready to share.', ?)", (daemon_id, now))
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "DAY_PLAN.md").write_text("# My plan\n- Painting")
    (ws / "AGENDA.md").write_text("## Threads\n- tides")
    (tmp_path / "creative_output" / "poem").mkdir(parents=True)
    (tmp_path / "creative_output" / "poem" / "tides.md").write_text("# Tides\n\nThe moon pulls.")
    return Room(tmp_path, daemon_id)


def test_nothing_shows_until_she_shares_it(room):
    feed = room.feed("kohl")
    assert feed["pieces"] == []
    assert room.piece("journal", "j-1", "kohl") is None
    assert room.share("journal", "j-1", note="Yesterday, finally done.")["shared"]
    feed = room.feed("kohl")
    assert [(p["kind"], p["id"], p["note"]) for p in feed["pieces"]] == \
        [("journal", "j-1", "Yesterday, finally done.")]
    assert room.piece("journal", "j-1", "kohl")["content"] == "A long day of building."
    assert room.piece("journal", "j-2", "kohl") is None, "an entry she didn't share stays hers"


def test_audiences(room):
    room.share("painting", "img-1", audience="house")
    room.share("writing", "poem/tides.md")  # Kohl only
    house = room.feed("house")
    assert [p["kind"] for p in house["pieces"]] == ["painting"]
    assert house["sections"] == [], "plan and agenda are Kohl's view for now"
    assert room.piece("writing", "poem/tides.md", "house") is None
    assert {p["kind"] for p in room.feed("kohl")["pieces"]} == {"painting", "writing"}
    assert room.section("day_plan", "house") is None


def test_painting_carries_what_she_said_and_its_file(room):
    room.share("painting", "img-1", note="For Kohl.")
    p = room.piece("painting", "img-1", "kohl")
    assert p["artist_note"] == "The light came out softer than I meant."
    assert p["why"] == "it stayed with me" and p["note"] == "For Kohl."
    assert p["image"] == "/room/pieces/painting/img-1/file"
    assert "image_path" not in p
    assert room.piece_file("painting", "img-1", "kohl").read_bytes().startswith(b"\x89PNG")


def test_unshare_and_standing_sections(room):
    room.share("journal", "j-1")
    assert room.unshare("journal", "j-1")["unshared"]
    assert room.piece("journal", "j-1", "kohl") is None
    assert "error" in room.unshare("journal", "j-1")
    assert room.feed("kohl")["sections"] == ["day_plan", "agenda", "homepage"]
    assert room.section("agenda", "kohl")["text"].startswith("## Threads")
    room.set_standing("agenda", False)
    assert room.section("agenda", "kohl") is None
    assert room.feed("kohl")["sections"] == ["day_plan", "homepage"]


def test_she_cant_share_what_isnt_there_or_outside(room):
    assert "error" in room.share("journal", "nope")
    assert "error" in room.share("writing", "../workspace/AGENDA.md")
    assert "error" in room.share("workspace", "../../etc/passwd")
    assert "error" in room.share("dream", "x")
    assert "error" in room.share("journal", "j-1", audience="everyone")
    assert room.feed("kohl")["pieces"] == []


def test_tokens_are_hashed_and_scoped(room, tmp_path):
    token = mint_token("house", "test", tmp_path)
    assert audience_for(token, tmp_path) == "house"
    assert audience_for(token + "x", tmp_path) is None
    assert audience_for(None, tmp_path) is None
    assert token not in (tmp_path / "room" / "tokens.json").read_text()


def test_her_tools(room):
    from handlers.room import execute_room_tool
    out = asyncio.run(execute_room_tool("share_to_room", {"kind": "painting", "id": "img-1",
                                                          "audience": "house"}, room=room))
    assert out["success"] and "the house" in out["result"]
    seen = asyncio.run(execute_room_tool("view_my_room", {}, room=room))["result"]
    assert seen["shared"][0]["id"] == "img-1"
    out = asyncio.run(execute_room_tool("set_room_section", {"section": "homepage", "on": False}, room=room))
    assert out["success"] and room.state()["standing"]["homepage"] is False
    assert not asyncio.run(execute_room_tool("share_to_room", {"kind": "journal", "id": "zz"}, room=room))["success"]


def test_feed_routes_need_a_room_token_and_only_read(room, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.room import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    room.share("painting", "img-1", note="hi")
    room.share("journal", "j-1")
    assert client.get("/room").status_code == 401
    assert client.get("/room", headers={"Authorization": "Bearer wrong"}).status_code == 401
    kohl = {"Authorization": f"Bearer {mint_token('kohl', 't', tmp_path)}"}
    house = {"Authorization": f"Bearer {mint_token('house', 't', tmp_path)}"}
    body = client.get("/room", headers=kohl).json()
    assert body["audience"] == "kohl" and {p["id"] for p in body["pieces"]} == {"img-1", "j-1"}
    assert client.get("/room", headers=house).json()["pieces"] == []
    assert client.get("/room/pieces/journal/j-1", headers=kohl).json()["content"] == "A long day of building."
    assert client.get("/room/pieces/journal/j-1", headers=house).status_code == 404
    assert client.get("/room/pieces/journal/j-2", headers=kohl).status_code == 404
    assert client.get("/room/pieces/painting/img-1/file", headers=kohl).content.startswith(b"\x89PNG")
    assert client.get("/room/sections/day_plan", headers=kohl).json()["text"].startswith("# My plan")
    assert client.post("/room", headers=kohl).status_code == 405


def test_route_guard_leaves_room_auth_to_the_room():
    from fastapi import FastAPI
    import route_guard
    from routes.room import router
    app = FastAPI()
    app.include_router(router)
    # level_for, not classify_routes: that one fills the guard's module-wide
    # table, which the real app's route-auth tests read afterwards.
    levels = {(m, path): route_guard.level_for(m, path, route)
              for m, path, route, _ in route_guard.iter_mounted_routes(app) if path.startswith("/room")}
    assert levels[("GET", "/room")] == route_guard.SELF
    assert set(levels.values()) == {route_guard.SELF}


@pytest.fixture
def homepage(room, tmp_path, monkeypatch):
    """Her homepage in tmp: index plus an about page, a stylesheet, and the
    painting from the room fixture placed on it."""
    import homepage as hp
    import homepage_turn
    monkeypatch.setattr(hp, "HOMEPAGE_DIR", tmp_path / "homepages")
    monkeypatch.setattr(homepage_turn, "her_daemon", lambda: ("cass", "Cass", room.daemon_id))
    hp.create_homepage("cass", "Cass", "tides and questions")
    hp.save_page("cass", "index", '<p>Hello. <a href="about.html">About</a></p>')
    hp.save_page("cass", "about", "<p>About me.</p>", title="about ~ cass")
    hp.save_stylesheet("cass", "body { color: teal; }")
    return hp


def test_room_shows_her_homepage_pages_as_cards(room, homepage):
    sec = room.section("homepage", "kohl")
    assert sec["exists"] and sec["stylesheet"].strip().startswith("body")
    slugs = [p["slug"] for p in sec["pages"]]
    assert slugs[0] == "index" and "about" in slugs
    assert 'href="about.html"' in sec["pages"][0]["html"]
    assert room.section("homepage", "house") is None


def test_she_can_place_a_painting_on_her_homepage(room, homepage, tmp_path):
    from homepage_turn import HomepageTools
    tools = HomepageTools("cass", "Cass", room.daemon_id, hp=homepage)
    listed = json.loads(tools.list_artifacts({}))["pieces"]
    assert any(p["type"] == "painting" and p["id"] == "img-1" for p in listed)
    out = json.loads(tools.place_piece({"kind": "painting", "piece_id": "img-1"}))
    assert out["filename"] == "painting-img-1.png"
    assert '<img src="assets/painting-img-1.png" alt="The tide">' in out["html"]
    assert tools.changes == ["placed painting img-1"]
    assert (tmp_path / "homepages" / "cass" / "assets" / "painting-img-1.png").read_bytes().startswith(b"\x89PNG")
    assert "error" in tools.place_piece({"kind": "journal", "piece_id": "j-1"})
    assert "error" in tools.place_piece({"kind": "painting", "piece_id": "nope"})
    # The room serves it to whoever sees the homepage, and nothing outside assets/.
    assert room.homepage_asset("painting-img-1.png", "kohl").is_file()
    assert room.homepage_asset("painting-img-1.png", "house") is None
    assert room.homepage_asset("../manifest.json", "kohl") is None


def test_homepage_asset_route(room, homepage, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.room import router
    homepage.place_piece("cass", room.daemon_id, "painting", "img-1")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    kohl = {"Authorization": f"Bearer {mint_token('kohl', 't', tmp_path)}"}
    r = client.get("/room/sections/homepage/assets/painting-img-1.png", headers=kohl)
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    assert client.get("/room/sections/homepage/assets/painting-img-1.png").status_code == 401
    assert client.get("/room/sections/homepage", headers=kohl).json()["pages"][0]["slug"] == "index"


def test_a_standing_section_can_be_opened_to_the_house(room):
    # Eris, 2026-11-24: "my homepage should be visible to the house, but today's
    # plan and agenda remain private for now".
    assert room.feed("house")["sections"] == []
    room.set_standing("day_plan", False)
    room.set_standing("agenda", False)
    out = room.set_standing("homepage", True, "house")
    assert "the house" in out["message"]
    assert room.feed("house")["sections"] == ["homepage"]
    assert room.feed("kohl")["sections"] == ["homepage"]
    assert room.section("agenda", "house") is None
    assert room.state()["standing_for"]["day_plan"] == "kohl"
    assert "error" in room.set_standing("homepage", True, "everyone")
