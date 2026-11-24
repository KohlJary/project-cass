"""find_memes: tasteful, new, seen with her own eyes, saved for sharing."""
import base64

import pytest

import memes


def _post(i, title="a meme", url=None, nsfw=False, cnsfw=False, community="memes", score=10):
    return {"post": {"id": i, "ap_id": f"https://x/post/{i}", "name": title, "nsfw": nsfw,
                     "url": url or f"https://img/{i}.png"},
            "community": {"name": community, "nsfw": cnsfw}, "counts": {"score": score}}


def test_candidates_filter_and_order():
    posts = [_post(1, score=5), _post(2, nsfw=True), _post(3, cnsfw=True), _post(4, url="https://x/page"),
             _post(5, title="NSFW lol"), _post(6, score=50), _post(7)]
    got = memes.candidates(posts, None, seen=["https://x/post/7"])
    assert [c["key"] for c in got] == ["https://x/post/6", "https://x/post/1"]


def test_topic_matches_a_stem_in_title_or_community():
    posts = [_post(1, community="programmer_humor"), _post(2, title="cats being cats"), _post(3)]
    assert [c["key"] for c in memes.candidates(posts, "programming", [])] == ["https://x/post/1"]
    assert [c["key"] for c in memes.candidates(posts, "ok", [])] == [c["key"] for c in memes.candidates(posts, None, [])]  # too short to filter
    assert [c["key"] for c in memes.candidates(posts, "cats", [])] == ["https://x/post/2"]


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


def test_find_shows_pictures_saves_them_and_remembers(data_dir, monkeypatch):
    png = b"\x89PNG fake"
    monkeypatch.setattr(memes, "_fetch_posts", lambda period: [_post(1), _post(2, score=99), _post(3)])

    class R:
        ok = True

        class raw:
            @staticmethod
            def read(n, decode_content=True):
                return png

    monkeypatch.setattr(memes.requests, "get", lambda *a, **k: R())
    out = memes.find_memes(count=2)
    assert [m["title"] for m in out["memes"]] == ["a meme", "a meme"]
    assert out["memes"][0]["file"] == "memes/2.png" and (data_dir / "memes" / "2.png").read_bytes() == png
    assert len(out["_images"]) == 2 and base64.b64decode(out["_images"][0]["data"]) == png
    again = memes.find_memes(count=4)  # only the one not yet shown
    assert [m["file"] for m in again["memes"]] == ["memes/3.png"]
    assert memes.find_memes()["memes"] == []


def test_a_failed_source_is_quiet(data_dir, monkeypatch):
    def boom(*a, **k):
        raise memes.requests.RequestException("down")

    monkeypatch.setattr(memes.requests, "get", boom)
    out = memes.find_memes()
    assert out["success"] and out["memes"] == []
